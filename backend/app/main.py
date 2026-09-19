"""
FastAPI application — Document Intake Assistant backend.

Routes:
  POST /api/chat              — process a user message
  GET  /api/state             — get current state + missing fields + document
  POST /api/state/manual-edit — directly override a field (from UI [Edit])
  POST /api/reset             — reset session
  GET  /api/document          — get current document text only
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .document_generator import generate_document
from .llm import get_llm_provider, LLMProvider
from .models import (
    ChatRequest,
    ChatResponse,
    ManualEditRequest,
    StateResponse,
)
from .state_manager import StateManager

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_manager: StateManager = StateManager()
_llm: LLMProvider = get_llm_provider()

_GREETING = (
    "Hello! I'm here to help you record your personal wishes. "
    "This is a guided process — I'll ask you a series of questions and "
    "build a draft Personal Wishes Document as we go.\n\n"
    "(Using LLM provider: Deterministic Mock)\n\n"
    "Let's start: What is your full legal name?"
)


@asynccontextmanager
async def _lifespan(app_: object):
    _manager.reset()
    _manager.add_message("assistant", _GREETING)
    yield


app = FastAPI(
    title="Document Intake Assistant",
    description="Conversational intake API for a Personal Wishes Document.",
    version="1.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tightened in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Process one turn of the conversation.

    Flow:
      1. Call LLM provider → ModelIntakeResponse
      2. Validate state_updates through StateManager (never directly applied)
      3. Merge validated updates into PersonalWishesState
      4. Generate updated document
      5. Return reply + state + document
    """
    _manager.add_message("user", request.message)

    try:
        llm_response = await _llm.process_turn(
            history=_manager.history,
            state=_manager.state,
            user_message=request.message,
        )
    except Exception as exc:
        # LLM failure is non-fatal — return a safe fallback
        fallback_reply = (
            "I'm having trouble processing that. "
            "Could you rephrase or try again?"
        )
        _manager.add_message("assistant", fallback_reply)
        return ChatResponse(
            reply=fallback_reply,
            state=_manager.state,
            document=generate_document(_manager.state),
            missing_fields=_manager.get_missing_fields(),
        )

    # Validate + merge
    rejected = _manager.apply_updates(llm_response.state_updates)
    # Rejected fields are silently dropped; they won't pollute state

    reply = llm_response.reply
    _manager.add_message("assistant", reply)

    return ChatResponse(
        reply=reply,
        state=_manager.state,
        document=generate_document(_manager.state),
        missing_fields=_manager.get_missing_fields(),
    )


@app.get("/api/state", response_model=StateResponse)
async def get_state() -> StateResponse:
    """Return current state, missing fields, and document."""
    return StateResponse(
        state=_manager.state,
        missing_fields=_manager.get_missing_fields(),
        document=generate_document(_manager.state),
    )


@app.post("/api/state/manual-edit", response_model=StateResponse)
async def manual_edit(request: ManualEditRequest) -> StateResponse:
    """
    Allow the user to directly correct a field value from the UI.

    Validates the field name and type before applying.
    """
    try:
        _manager.apply_manual_edit(request.field, request.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    return StateResponse(
        state=_manager.state,
        missing_fields=_manager.get_missing_fields(),
        document=generate_document(_manager.state),
    )


@app.post("/api/reset")
async def reset() -> dict:
    """Reset the session — clear all state and conversation history."""
    _manager.reset()
    _manager.add_message("assistant", _GREETING)
    return {
        "ok": True,
        "reply": _GREETING,
        "state": _manager.state.model_dump(),
        "document": generate_document(_manager.state),
        "missing_fields": _manager.get_missing_fields(),
    }


@app.get("/api/document")
async def get_document() -> dict:
    """Return the current draft document text."""
    return {"document": generate_document(_manager.state)}
