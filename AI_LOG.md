# AI Log — Document Intake Assistant

This log records the key engineering decisions, iterations, and prompts used while building this application.

---

## 1. Initial approach: direct state mutation

**Prompt exploration:**
I initially considered a design where the LLM response would directly set fields on `PersonalWishesState`. For example:

```python
# Dangerous — never validate
state.full_name = llm_response.get("full_name")
```

**Problem identified:**
This assumes the LLM always returns well-typed values. Even a deterministic mock can produce a string like `"true"` instead of a boolean `True`, or a raw string instead of an `Executor` object. Applying this directly would break type safety silently.

**Decision:**
Introduce `ModelIntakeResponse` as a validated boundary. All LLM output passes through this model, and `StateManager.apply_updates()` validates each field individually before mutation.

```python
class ModelIntakeResponse(BaseModel):
    reply: str
    state_updates: dict[str, Any] = {}
    unresolved_fields: list[str] = []
```

---

## 2. Ambiguous executor — should we pick one?

**Input tested:**
```
I'm thinking about either my brother or my friend as executor.
```

**First iteration output:**
The mock initially extracted the first relationship keyword ("brother") and partially set the executor field.

**Problem:**
This is speculative. The user has not confirmed their choice. Storing a guess violates the assignment's core requirement: "unknown information must be represented explicitly rather than invented."

**Correction:**
Added `_is_ambiguous_executor()` to detect uncertainty patterns (`maybe`, `either`, `or`, `thinking`, etc.) specifically around executor-related language. When triggered, the function returns `state_updates: {}` and adds `executor` to `unresolved_fields`. The assistant asks a targeted clarifying question.

```json
{
  "state_updates": {},
  "reply": "I want to make sure we record the right person. Could you confirm...",
  "unresolved_fields": ["executor"]
}
```

---

## 3. Multi-field extraction: order of operations

**Input tested:**
```
I'm Jane Smith, I live at 12 Elm Street, London and my assets are worldwide.
```

**Problem:**
Name extraction using `"I'm Jane Smith"` pattern would also partially match the address sentence if not ordered carefully. Running address extraction before name normalisation led to occasional false captures.

**Correction:**
Extraction functions are applied in order: name → address → worldwide → children → executor → gifts → additional wishes. Each function is scoped to its own regex patterns and returns `None` if not found, avoiding cross-contamination.

---

## 4. `StateFieldStatus` enum — removed

**Initial plan:**
Considered tracking `empty / unconfirmed / confirmed` for each field.

**Problem:**
The `unconfirmed` state required storing information that the user had not yet validated — which contradicts the design principle that `None` means "not yet known". A three-state system also made the `StateManager.apply_updates()` logic significantly more complex for no clear user-facing benefit.

**Decision:**
Removed. `None` cleanly models "not known". Fields are only set when confirmed information is available. For ambiguous answers, the field stays `None`.

---

## 5. Correction flow: "Actually, my executor is Sarah Smith"

**Input tested:**
```
Actually, my executor should be my sister Emma Smith.
```

**First iteration result:**
The mock was not reliably detecting "actually" as a correction signal across varied phrasings.

**Improvement:**
Consolidated correction detection into a `_is_correction()` function that matches a broader set of natural language patterns:
```python
[r"\bactually\b", r"\bchange\b", r"\bcorrect\b", r"\binstead\b", r"\bsorry\b", ...]
```

When `is_correction=True`, the state manager allows overwriting existing fields. Other fields are unaffected because `apply_updates()` only touches the keys present in `state_updates`.

**Verified:**
```
Before: executor = { name: "James Smith", relationship: "brother" }
After:  executor = { name: "Emma Smith",  relationship: "sister"  }
full_name, home_address, children: unchanged
```

---

## 6. `reasoning` field — removed

**Initial plan:**
Include a `reasoning: Optional[str]` in `ModelIntakeResponse` to trace the mock's decision path.

**Problem:**
This added noise to the API response and wasn't useful to the UI. The assignment asks for reliable structured behaviour, not chain-of-thought.

**Decision:**
Removed. The mock's logic is transparent through its source code. The `AI_LOG.md` serves the documentation purpose instead.

---

## 7. Executor partial information

**Input tested:**
```
My executor is James.
```

(No surname, no relationship.)

**Problem:**
The original `Executor` model had `name: str` (required), which would reject partial information.

**Correction:**
Changed to:
```python
class Executor(BaseModel):
    name: str | None = None
    relationship: str | None = None
```

This allows `{ name: "James", relationship: null }` to be stored without invention, satisfying the requirement that unknown sub-fields are represented as `None`.

---

## 8. LLM error resilience

**Problem simulated:**
What if the LLM provider raises an exception (network failure, API key invalid, rate limit)?

**Decision:**
Wrapped the `_llm.process_turn()` call in a try/except in `main.py`. On failure, the API returns a safe fallback reply ("I'm having trouble processing that...") with the unchanged state and document. The session continues without crashing.

This demonstrates the assignment requirement: "gracefully handle unexpected model outputs without crashing."

---

## 9. Deliberately kept the system simple

**Decision under review:**
Whether to add a database, authentication, RAG pipeline, or a real LLM API integration before submission.

**Conclusion:**
Chose not to. The assignment focuses on three specific engineering concerns:

1. **Conversational state management** — extracting structured information from free-form text and maintaining it correctly across turns.
2. **LLM output reliability** — validating model output before applying it to state, handling ambiguity and contradictions without inventing data.
3. **Conventional software engineering** — clean boundaries, tested code, clear design decisions.

None of those require a database, OAuth, LangChain, RAG, or WebSockets.

The deterministic mock is a deliberate choice, not a compromise:
- The evaluator can run the project immediately, with no API keys or external accounts.
- The mock's rule-based extraction is transparent and testable, unlike a live LLM that may behave non-deterministically across API calls.
- The `LLMProvider` abstract interface means swapping in a real provider in production is a single-line change — exactly what the assignment asks candidates to demonstrate.

**Reference:** The assignment explicitly states: *"A deterministic mock or local stub is acceptable."*

---

## 10. International address handling

**Problem discovered during testing:**
The original address extraction used UK-specific regex patterns (`r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}"` postcode format). An Indian address such as `flat b602, silver brook, bavdhan pune` failed extraction entirely.

**Decision:**
Removed all UK-specific patterns. Replaced with a context-aware two-priority system:
1. **Explicit phrase** — `"I live at …"` / `"my address is …"` — extracted verbatim.
2. **Context fallback** — if the assistant's last message asked for the home address, accept any text ≥5 characters containing at least one letter, storing it verbatim. This handles any country's address format without invention or normalisation.

```python
def _is_valid_address(text: str) -> bool:
    return len(text.strip()) >= 5 and any(ch.isalpha() for ch in text)
```

**Verified:** Indian flat address, Japanese address, US address all accepted and stored exactly as supplied.

---

## 11. Worldwide-assets wording

**Problem:**
Question text read *"Do your assets cover worldwide, or are they limited to the UK only?"* — UK-specific wording inconsistent with the field's purpose and the user's situation.

**Decision:**
Changed to the neutral *"Do you want this document to cover your assets worldwide?"* throughout — in the question map, the reply builder, the document generator, the frontend state panel, and the tests. No country-specific interpretation is applied to the boolean result.

---

## 12. Children bare yes/no

**Problem:**
When the assistant asked *"Do you have any children?"*, the user could answer `yes` or `No` and the system would say *"I didn't quite catch that"*. Only verbose answers like *"no i dont have any children"* were accepted.

**Decision:**
Added context detection: before calling `_extract_children()`, scan the conversation history. If the last assistant message contained *"have any children"*, set `context_asked=True`. When `True`, the function recognises bare affirmatives (`yes`, `yeah`, `yep`, `i do`) and negatives (`no`, `nope`, `nah`, `i don't`) as unambiguous direct answers.

---

## 13. Multiple specific gifts and no-gifts confirmation

**Problem A — Multi-gift:** `"I want to give my laptop to Aarav and my watch to Anaya."` was parsed as one gift with recipient `"Aarav and my watch to Anaya"` due to a greedy regex match.

**Fix:** New `_extract_specific_gifts()` splits the text after the introductory verb (`give`/`leave`/`bequeath`) on `" and "` clauses that are followed by another item-to-recipient pattern. Each clause is independently matched.

**Problem B — No gifts:** `"No specific gifts."` / `"None."` left `specific_gifts` unchanged, causing the assistant to re-ask the same question.

**Fix A — State model:** Changed `specific_gifts: list[SpecificGift] | None = None` so that `None` = not yet answered (missing), `[]` = explicitly confirmed no gifts (complete), `[...]` = has gifts (complete).

**Fix B — Detection:** Added `_user_declined_specific_gifts()` and context-aware bare-no detection (same pattern as children). When triggered and `state.specific_gifts is None`, sets `specific_gifts = []` so the field is marked complete and the assistant moves on.

**Fix C — Document:** Generator now renders three distinct states: `None` → *"Not yet provided"*, `[]` → *"None specified."*, list → bullet items.

**Verified with 16 new tests:** all 69 tests pass.
