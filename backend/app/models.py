"""
Pydantic models for the Document Intake Assistant.

PersonalWishesState is the single source of truth.
All fields default to None (unknown) — information is only
stored when it has been explicitly confirmed by the user.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

class Executor(BaseModel):
    """Appointed executor. Fields are individually nullable so partial
    information (e.g. name only) can be represented without invention."""
    name: str | None = None
    relationship: str | None = None


class SpecificGift(BaseModel):
    """A specific bequest from the testator."""
    recipient: str
    description: str


class PersonalWishesState(BaseModel):
    """
    Structured state for a Personal Wishes Document intake session.

    None == not yet known / not yet confirmed.
    A real value == confirmed by the user.
    """
    full_name: str | None = None
    home_address: str | None = None
    covers_worldwide_assets: bool | None = None
    has_children: bool | None = None
    children_names: list[str] = []
    executor: Executor | None = None
    specific_gifts: list[SpecificGift] | None = None
    additional_wishes: str | None = None


# ---------------------------------------------------------------------------
# LLM interface models
# ---------------------------------------------------------------------------

class ModelIntakeResponse(BaseModel):
    """
    Structured response returned by the LLM layer.

    reply            — conversational follow-up to send to the user.
    state_updates    — dict of validated field deltas to merge into state.
    unresolved_fields — fields mentioned but not yet confirmable (ambiguous).
    """
    reply: str
    state_updates: dict[str, Any] = {}
    unresolved_fields: list[str] = []


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be empty")
        return v


class ChatResponse(BaseModel):
    reply: str
    state: PersonalWishesState
    document: str
    missing_fields: list[str]


class ManualEditRequest(BaseModel):
    """Direct field override — used when the user clicks [Edit] in the UI."""
    field: str
    value: Any


class StateResponse(BaseModel):
    state: PersonalWishesState
    missing_fields: list[str]
    document: str
