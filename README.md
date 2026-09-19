# Document Intake Assistant

A conversational intake application that collects information through guided dialogue and generates a live draft **Personal Wishes Document**.


---

## Overview

The application conducts a structured interview with the user, extracts information from natural language replies, validates it against a strict schema, and generates a continuously updating document preview — all without requiring a paid LLM API.

---

## Architecture

```
React (TypeScript + Vite)
        │
        │ HTTP
        ▼
    FastAPI
        │
   ┌────┴────────┐
   ▼             ▼
MockLLM      StateManager
   │             │
   ▼             ▼
ModelIntakeResponse  PersonalWishesState (Pydantic)
        │
        ▼
 DocumentGenerator
        │
        ▼
 React Document Preview
```

**Key design principle**: the LLM output (`ModelIntakeResponse`) is always **validated through Pydantic before mutating state**. Raw LLM output never directly touches the live `PersonalWishesState`.

---

## Tech Stack

| Layer     | Technology                          |
|-----------|-------------------------------------|
| Frontend  | React 19, TypeScript, Vite          |
| Styling   | Vanilla CSS (design tokens, no Tailwind) |
| Backend   | Python 3.12, FastAPI                |
| Validation| Pydantic v2                         |
| LLM layer | Deterministic Mock (no API key required) |
| Testing   | Pytest, pytest-asyncio, FastAPI TestClient |

---

## Running Locally

### 1. Backend

```powershell
# From repo root
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt

# Start server (port 8000)
.venv\Scripts\uvicorn backend.app.main:app --reload --port 8000
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev   # runs at http://localhost:5173
```

Open **http://localhost:5173** in your browser.

---

## API Contract

| Method | Path                     | Description                          |
|--------|--------------------------|--------------------------------------|
| POST   | `/api/chat`              | Process a user message               |
| GET    | `/api/state`             | Get current state + missing fields   |
| POST   | `/api/state/manual-edit` | Directly override a field            |
| POST   | `/api/reset`             | Reset the session                    |
| GET    | `/api/document`          | Get current document text            |

### `/api/chat` — request
```json
{ "message": "My name is Jane Smith." }
```

### `/api/chat` — response
```json
{
  "reply": "Thank you, Jane. What is your home address?",
  "state": { "full_name": "Jane Smith", "... ": "..." },
  "document": "── ... FICTIONAL — NOT LEGAL ADVICE ...",
  "missing_fields": ["home_address", "covers_worldwide_assets", "..."]
}
```

---

## How the Mock LLM Works

The `MockLLMProvider` uses deterministic regex-based extraction. It handles:

| Scenario | Example Input | Behaviour |
|----------|--------------|-----------|
| Single field | "My name is Jane Smith." | Extracts `full_name` |
| Multi-field | "I'm Jane Smith, 12 Elm St, worldwide assets." | Extracts name + address + worldwide |
| No children | "I don't have children." | Sets `has_children = false` |
| Named children | "I have Alice and Ben." | Sets `has_children = true`, names list |
| Executor | "My brother James Smith." | Extracts name + relationship |
| Multiple gifts | "Give my laptop to Aarav and watch to Anaya." | Extracts two separate bequests |
| No gifts | "No specific gifts." / "None." | Sets `specific_gifts = []` |
| Ambiguous | "Maybe my brother or a friend." | No state update — asks clarification |
| Contradiction | "I don't have children." → "My daughter Alice..." | No state update — asks clarification |
| Correction | "Actually, make it Sarah Smith." | Overwrites executor, preserves other fields |

The mock sits behind the same `LLMProvider` interface that a production LLM would use.

---

## Structured State

```python
class PersonalWishesState(BaseModel):
    full_name: str | None = None
    home_address: str | None = None
    covers_worldwide_assets: bool | None = None
    has_children: bool | None = None
    children_names: list[str] = []
    executor: Executor | None = None        # { name, relationship }
    specific_gifts: list[SpecificGift] | None = None  # None=unanswered, []=no gifts, [...]= gifts
    additional_wishes: str | None = None
```

`None` means **not yet known**. Information is never invented or guessed.

---

## Error Handling

- **Invalid LLM output**: State updates are validated by Pydantic before application. Rejected fields are silently dropped — the session continues.
- **LLM exception**: FastAPI returns a safe fallback reply. The session does not crash.
- **Unknown field in manual edit**: Returns HTTP 422.
- **Empty message**: Returns HTTP 422 (Pydantic validator).

---

## Tests

```powershell
.venv\Scripts\pytest -v
```

Test coverage (69 tests):
- `test_state.py` — schema, merge, correction, invalid rejection, strict validation, reset
- `test_mock_llm.py` — all extraction scenarios including multi-gift, no-gift, context-aware yes/no
- `test_chat.py` — API integration (chat, manual-edit, reset)
- `test_document.py` — document generation, disclaimer, all gift states

---

## Design Decisions

**Why validate before applying state updates?**
The LLM (even a deterministic mock) could produce malformed field values. Validating through Pydantic before mutation ensures the source of truth is always structurally correct, regardless of LLM behaviour.

**Why `None` instead of a `StateFieldStatus` enum?**
`None` cleanly represents "not yet confirmed". For ambiguous inputs, the state simply isn't updated — preserving the requirement that uncertain information is never stored.

**Why keep the mock behind an abstract interface?**
`MockLLMProvider` implements `LLMProvider` exactly as a real provider would. Swapping in a production LLM requires changing one line (`get_llm_provider()`) — no other code changes.

**Why in-memory state?**
For an interview demo with a single evaluator session, a database adds complexity without demonstrating anything relevant to the task. See `PRODUCTION_NOTES.md` for how this would be extended.

---
