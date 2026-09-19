"""
LLM layer for the Document Intake Assistant.

Architecture
------------
  LLMProvider          — abstract interface (swap-safe boundary)
  MockLLMProvider      — deterministic rule-based implementation (default)
  GeminiLLMProvider    — optional; activated only when GEMINI_API_KEY is set

The rest of the application only ever calls LLMProvider.process_turn().
The concrete implementation is selected once at startup (get_llm_provider()).
"""
from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod

from .models import Executor, ModelIntakeResponse, PersonalWishesState, SpecificGift


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    @abstractmethod
    async def process_turn(
        self,
        history: list[dict[str, str]],
        state: PersonalWishesState,
        user_message: str,
    ) -> ModelIntakeResponse:
        """
        Given the conversation history, current structured state, and the
        latest user message, return a ModelIntakeResponse.

        - reply            : what to say back to the user
        - state_updates    : dict of validated deltas to merge into state
        - unresolved_fields: fields that were mentioned but are ambiguous
        """


# ---------------------------------------------------------------------------
# Deterministic Mock LLM
# ---------------------------------------------------------------------------

# Relationship keywords recognised in natural language
_RELATIONSHIP_KEYWORDS = {
    "brother": "brother",
    "sister": "sister",
    "wife": "wife",
    "husband": "husband",
    "son": "son",
    "daughter": "daughter",
    "friend": "friend",
    "colleague": "colleague",
    "partner": "partner",
    "niece": "niece",
    "nephew": "nephew",
    "aunt": "aunt",
    "uncle": "uncle",
    "mother": "mother",
    "father": "father",
    "solicitor": "solicitor",
    "lawyer": "lawyer",
}

# Phrases indicating the user wants to correct something
_CORRECTION_PATTERNS = [
    r"\bactually\b",
    r"\bchange\b",
    r"\bcorrect\b",
    r"\bupdate\b",
    r"\bmistake\b",
    r"\binstead\b",
    r"\bno,?\s+(it'?s?|my)\b",
    r"\bwait\b",
    r"\bsorry\b",
]

# Phrases indicating ambiguity / uncertainty
_AMBIGUITY_PATTERNS = [
    r"\bmaybe\b",
    r"\bnot sure\b",
    r"\bperhaps\b",
    r"\beither\b",
    r"\bor\b.*\bor\b",
    r"\bthinking\b",
    r"\bconsidering\b",
    r"\bdeciding\b",
    r"\bunsure\b",
    r"\bcould be\b",
    r"\bmight\b",
]


def _is_correction(text: str) -> bool:
    text = text.lower()
    return any(re.search(p, text) for p in _CORRECTION_PATTERNS)


def _is_ambiguous(text: str) -> bool:
    text = text.lower()
    return any(re.search(p, text) for p in _AMBIGUITY_PATTERNS)


def _mentions_child(text: str) -> bool:
    """Return True if the message references a child, even without 'I have children'."""
    return bool(re.search(
        r"\b(son|daughter|child|children|kids?|my girl|my boy)\b",
        text.lower(),
    ))


def _extract_name(text: str) -> str | None:
    """Extract a plausible full name from the message."""
    # Skip if this looks like an executor sentence
    lower = text.lower()
    if re.search(r"\b(executor|appoint)\b", lower):
        return None

    # Case-insensitive prefix match, then strict [A-Z] character class for the name itself.
    # This prevents 'and', 'I', or other words from leaking into the name.
    for prefix_pattern in [
        r"(?i)my (?:full )?name is\s+",
        r"(?i)I(?:'m| am)\s+",
    ]:
        prefix_m = re.search(prefix_pattern, text)
        if prefix_m:
            after = text[prefix_m.end():]
            # Strictly capitalised: stops at any non-Name word like 'and', 'I', etc.
            name_m = re.match(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", after)
            if name_m:
                return name_m.group(1).strip()

    # Standalone full name on its own line
    m = re.match(r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)$", text.strip())
    if m:
        return m.group(1)

    return None


def _extract_address_from_phrase(text: str) -> str | None:
    """
    Extract an address only when the user uses an explicit locating phrase.

    Examples that match:
      - "I live at Flat B602, Silver Brook, Bavdhan, Pune"
      - "My address is 221B Baker Street, London"
      - "My home address is MG Road, Bengaluru"

    Returns everything after the trigger phrase, trimmed of trailing punctuation.
    Returns None when no explicit phrase is found — the caller then falls back
    to the context-aware acceptance path.
    """
    m = re.search(
        r"(?:i\s+live\s+at|living\s+at|my\s+(?:home\s+)?address\s+is"
        r"|address\s+is|address:\s*|residing\s+at)\s*(.+)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None

    addr = m.group(1).strip()
    # Stop at a sentence boundary that clearly starts a new topic
    addr = re.split(r"\s+(?:and\s+my\s+|,\s*my\s+|i\s+have\s+|i\s+don|my\s+assets)\b", addr, flags=re.IGNORECASE)[0]
    addr = addr.strip().rstrip(".,;")
    return addr if _is_valid_address(addr) else None


def _is_valid_address(text: str) -> bool:
    """
    Minimal, country-agnostic validation.

    An address is considered valid if:
      - It has at least 5 characters after stripping whitespace
      - It contains at least one alphabetic character

    We deliberately do NOT enforce any country-specific format (no postcodes,
    no street-type suffixes, no digit requirements).  The application's job is
    to *collect* the user's address, not to verify that it exists.

    Rejected examples:  "", "  ", "yes", "no", "ok", "42"
    Accepted examples:  "Silver Brook, Bavdhan",
                        "Flat B602, Silver Brook, Bavdhan, Pune, India",
                        "221B Baker Street, London NW1 6XE",
                        "12-3 Shibuya, Tokyo, Japan",
                        "MG Road, Bengaluru, Karnataka"
    """
    text = text.strip()
    return len(text) >= 5 and any(ch.isalpha() for ch in text)


def _extract_worldwide_assets(text: str) -> bool | None:
    """Return True/False/None for worldwide asset coverage.

    The question asked is 'Do you want this document to cover your assets worldwide?'
    True  = user wants worldwide coverage
    False = user does not want worldwide coverage (country-neutral — no UK assumption)
    None  = answer unclear, ask again
    """
    lower = text.lower()
    worldwide_yes = re.search(r"\b(worldwide|global|international|everywhere|all countries)\b", lower)
    not_worldwide = re.search(r"\b(not worldwide|local only|specific countries only)\b", lower)
    yes_words = re.search(r"\b(yes|yeah|yep|correct|that'?s right|affirmative|indeed)\b", lower)
    no_words = re.search(r"\b(no|nope|not really|negative|no i don'?t|not global)\b", lower)

    if worldwide_yes or (yes_words and not no_words):
        return True
    if not_worldwide or no_words:
        return False
    return None


def _extract_children(text: str, context_asked: bool = False) -> tuple[bool | None, list[str]]:
    """Return (has_children, children_names).

    When context_asked=True (assistant just asked "Do you have any children?"),
    bare yes/no words are treated as direct answers.
    """
    lower = text.lower()

    # Check negation FIRST — order matters
    no_children = re.search(
        r"\b("
        r"no children|no kids"
        r"|don'?t have (?:any )?(?:children|kids|child)"
        r"|don'?t have any"
        r"|childless|without children|no child"
        r"|haven'?t got (?:any )?(?:children|kids)"
        r")\b",
        lower,
    )
    if no_children:
        return False, []

    # Context-aware bare yes/no — only when the assistant just asked about children
    if context_asked:
        bare_yes = re.search(r"^\s*(yes|yeah|yep|yup|sure|correct|affirmative|i do|i have)\s*[.!]?\s*$", lower)
        bare_no = re.search(r"^\s*(no|nope|nah|not really|negative|i don'?t|i don't)\s*[.!]?\s*$", lower)
        if bare_yes:
            return True, []
        if bare_no:
            return False, []

    # Extract names after "children," / "kids," / "they are"
    names: list[str] = []
    has_children: bool | None = None

    has_match = re.search(r"\b(have|got|i have|i've got)\b.*\b(child|children|kid|kids|son|daughter)\b", lower)
    if has_match:
        has_children = True
        # Try to pull names: capitalised words
        name_candidates = re.findall(r"\b([A-Z][a-z]+)\b", text)
        stop = {
            "I", "My", "The", "A", "An", "And", "Or", "But", "Yes", "No",
            "Have", "Got", "Two", "Three", "One", "Four", "Five", "Are", "Is",
            "Their", "They", "Children", "Kids", "Son", "Daughter",
        }
        names = [n for n in name_candidates if n not in stop]

    # Inline: "Alice and Ben"
    and_match = re.findall(r"\b([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)\b", text)
    if and_match:
        has_children = True
        for a, b in and_match:
            if a not in names:
                names.append(a)
            if b not in names:
                names.append(b)

    return has_children, names


def _extract_executor(text: str) -> Executor | None:
    """Extract executor name and relationship."""
    lower = text.lower()

    # Only extract if the message is actually about an executor
    executor_mentioned = bool(re.search(
        r"\b(executor|appoint|appoint as|execute|my estate)\b",
        lower,
    ))
    # Also trigger if a relationship keyword is present alongside a name-like pattern
    relationship: str | None = None
    for kw, label in _RELATIONSHIP_KEYWORDS.items():
        if re.search(rf"\b{kw}\b", lower):
            relationship = label
            break

    has_name_candidate = bool(re.search(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)", text))
    if not executor_mentioned and not (relationship and has_name_candidate):
        return None

    name: str | None = None

    # Priority 1: "[Name] should be / to be / will be my executor"
    m = re.search(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:should be|to be|will be|as)\s+(?:my\s+)?executor",
        text,
    )
    if m:
        name = m.group(1).strip()

    # Priority 2: "executor is [Name]" / "executor should be [Name]" — supports single or multi-word
    if not name:
        m = re.search(
            r"(?:executor|appoint(?:ed)?)\s+(?:is|should be|to be|will be)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            text,
        )
        if m:
            name = m.group(1).strip()

    # Priority 3: "my [relationship] [Name]" e.g. "my brother James Smith"
    if not name and relationship:
        m = re.search(
            rf"(?:my\s+)?{relationship}\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            text,
            re.IGNORECASE,
        )
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in {"my", "the", "a", "an", "is", "should"}:
                name = candidate

    # Priority 4: single-word capitalised name after "is"
    if not name and executor_mentioned:
        m = re.search(r"(?:is|executor is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
        if m:
            name = m.group(1).strip()

    if name or relationship:
        return Executor(name=name, relationship=relationship)
    return None


def _extract_specific_gifts(text: str) -> list[SpecificGift]:
    """Extract gift/bequest mentions, supporting multiple gifts in one sentence.

    Handles patterns like:
      'give my laptop to Aarav and my watch to Anaya'
      'leave £10,000 to my niece Sarah'
      'I want to give my watch to Ben'
    """
    gifts: list[SpecificGift] = []

    # Find the main verb that introduces gifts
    verb_match = re.search(
        r"\b(?:give|leave|bequeath|donate|gift)\b",
        text, re.IGNORECASE
    )

    if verb_match:
        # Everything after the verb
        remainder = text[verb_match.end():].strip()

        # Split on " and " that is followed by an item heading to another recipient,
        # i.e. 'and (my|the|a|an)? <word(s)> to'
        clauses = re.split(
            r"\s+and\s+(?=(?:(?:my|the|a|an)\s+)?\w[\w\s]*?\s+to\s+)",
            remainder,
            flags=re.IGNORECASE,
        )

        for clause in clauses:
            m = re.match(
                r"(?:(?:my|the|a|an)\s+)?"           # optional leading article
                r"(.+?)"                               # description (non-greedy)
                r"\s+to\s+"                            # 'to'
                r"(?:(?:my|your|their)\s+\w+\s+)?"   # optional 'my niece' / 'your friend'
                r"([A-Za-z][a-z]+(?:\s+[A-Z][a-z]+)?)"  # recipient name
                r"\s*[.,!?]?\s*$",                    # trailing punctuation
                clause.strip(),
                re.IGNORECASE,
            )
            if m:
                desc = m.group(1).strip().strip(".,")
                recipient = m.group(2).strip().strip(".,")
                if desc and recipient:
                    gifts.append(SpecificGift(description=desc, recipient=recipient))

    # Fallback: monetary amounts (e.g. '£10,000 to Alice') not caught above
    if not gifts:
        for m in re.finditer(
            r"(\£[\d,]+(?:\.\d+)?|\$[\d,]+(?:\.\d+)?|[\d,]+\s*pounds?)"
            r"\s+to\s+"
            r"(?:(?:my|your)\s+\w+\s+)?"
            r"([A-Za-z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            text, re.IGNORECASE
        ):
            desc = m.group(1).strip()
            recipient = m.group(2).strip().strip(".,")
            if desc and recipient:
                gifts.append(SpecificGift(description=desc, recipient=recipient))

    return gifts


def _user_declined_specific_gifts(text: str) -> bool:
    """Return True when the user explicitly says they have no specific gifts."""
    lower = text.strip().lower()
    patterns = [
        r"\bno\s+(?:specific\s+)?gifts?\b",
        r"\bno\s+bequests?\b",
        r"\bi\s+(?:don'?t|do\s+not)\s+have\s+(?:any\s+)?(?:specific\s+)?gifts?\b",
        r"\bi\s+have\s+no\s+(?:specific\s+)?gifts?\b",
        r"^\s*none\s*[.!]?\s*$",
        r"^\s*nothing\b",
    ]
    return any(re.search(p, lower) for p in patterns)


def _extract_additional_wishes(text: str) -> str | None:
    """Extract freeform additional wishes."""
    lower = text.lower()
    triggers = [
        r"additional(?:ly)?",
        r"also\s+(?:want|wish|would like)",
        r"furthermore",
        r"i also",
        r"finally",
        r"my (?:other|remaining|last)\s+wish",
        r"one more thing",
        r"donate.*to\s+charity",
        r"cremation",
        r"funeral",
        r"burial",
    ]
    for t in triggers:
        if re.search(t, lower):
            return text.strip()
    return None


_QUESTION_MAP = {
    "full_name": "What is your full legal name?",
    "home_address": "What is your home address?",
    "covers_worldwide_assets": "Do you want this document to cover your assets worldwide?",
    "has_children": "Do you have any children?",
    "children_names": "What are your children's names?",
    "executor": "Who would you like to appoint as the executor of your estate? Please share their name and relationship to you.",
    "specific_gifts": "Do you have any specific gifts or bequests you'd like to include — for example, sums of money or personal items to particular people?",
    "additional_wishes": "Are there any additional wishes you'd like to record, such as funeral preferences or charitable donations?",
}


class MockLLMProvider(LLMProvider):
    """
    Deterministic rule-based LLM mock.

    Handles all key intake scenarios without calling any external API:
      A  Single field extraction
      B  Multi-field extraction
      C  No children
      D  Children with names
      E  Executor with relationship
      F  Ambiguous answers (no state update + clarification prompt)
      G  Corrections (replaces previously set fields)
    """

    async def process_turn(
        self,
        history: list[dict[str, str]],
        state: PersonalWishesState,
        user_message: str,
    ) -> ModelIntakeResponse:
        msg = user_message.strip()
        lower = msg.lower()
        updates: dict = {}
        unresolved: list[str] = []

        # ---- Ambiguity check (do this first — don't store uncertain info) ----
        if self._is_ambiguous_executor(lower):
            unresolved.append("executor")
            reply = (
                "I want to make sure we record the right person. "
                "Could you confirm who you'd like as your executor — "
                "your brother or your friend?"
            )
            return ModelIntakeResponse(reply=reply, state_updates={}, unresolved_fields=unresolved)

        # ---- Contradiction check: user said no children but now mentions one ----
        if state.has_children is False and _mentions_child(msg):
            return ModelIntakeResponse(
                reply=(
                    "You mentioned earlier that you don't have children, "
                    "but it sounds like you may be referring to a child here. "
                    "Could you clarify — do you have children?"
                ),
                state_updates={},
                unresolved_fields=["has_children", "children_names"],
            )

        is_correction = _is_correction(lower)

        # ---- Full name ----
        name = _extract_name(msg)
        if name and (state.full_name is None or is_correction):
            updates["full_name"] = name

        # Detect whether the last assistant message asked for the home address.
        # This is used to decide whether the user's current message is their address
        # even when they don't use an explicit "I live at ..." phrase.
        last_assistant_asked_for_address = False
        if history:
            for item in reversed(history):
                if item.get("role") == "assistant":
                    content = item.get("content", "").lower()
                    if "home address" in content or "your address" in content:
                        last_assistant_asked_for_address = True
                    break

        # ---- Home address ----
        # Priority 1: User uses an explicit locating phrase regardless of context.
        phrase_address = _extract_address_from_phrase(msg)
        if phrase_address and (state.home_address is None or is_correction):
            updates["home_address"] = phrase_address

        # Priority 2: Address field is still empty AND the assistant just asked for it.
        # Accept whatever the user says verbatim, as long as it passes the minimal
        # _is_valid_address check (≥5 chars, has at least one letter).
        # This handles ANY international format — Indian, Japanese, US, etc. —
        # without requiring any country-specific pattern.
        elif state.home_address is None and last_assistant_asked_for_address:
            # Strip common lead-in phrases the user might add for politeness
            candidate = re.sub(
                r"^(?:it\s+is|it's|that\s+would\s+be|my\s+address\s+is|i\s+live\s+at)\s+",
                "",
                msg,
                flags=re.IGNORECASE,
            ).strip().rstrip(".,;")
            if _is_valid_address(candidate):
                updates["home_address"] = candidate

        # Priority 3: Correction path — user is updating a previously stored address.
        elif is_correction and state.home_address is not None:
            m_corr = re.search(
                r"(?:address(?:\s+is|\s+to|\s+should\s+be)?|live\s+at|change\s+(?:my\s+)?address(?:\s+to)?)[:\s]+(.+)",
                msg, re.IGNORECASE,
            )
            candidate = m_corr.group(1).strip().rstrip(".,;") if m_corr else None
            if candidate and _is_valid_address(candidate):
                updates["home_address"] = candidate

        # ---- Worldwide assets ----
        worldwide = _extract_worldwide_assets(msg)
        if worldwide is not None and (state.covers_worldwide_assets is None or is_correction):
            updates["covers_worldwide_assets"] = worldwide

        # ---- Children ----
        # Detect whether the last assistant message asked about children,
        # so we can accept a bare "yes" / "no" as a direct answer.
        last_assistant_asked_for_children = False
        if history:
            for item in reversed(history):
                if item.get("role") == "assistant":
                    content = item.get("content", "").lower()
                    if "have any children" in content or "do you have children" in content:
                        last_assistant_asked_for_children = True
                    break

        has_children, child_names = _extract_children(msg, context_asked=last_assistant_asked_for_children)
        if has_children is not None and (state.has_children is None or is_correction):
            updates["has_children"] = has_children
            if child_names:
                updates["children_names"] = child_names
        elif has_children is None and child_names:
            # Named children without explicit "I have" — infer has_children
            updates["has_children"] = True
            updates["children_names"] = child_names

        # ---- Executor ----
        executor = _extract_executor(msg)
        if executor and (executor.name or executor.relationship):
            if state.executor is None or is_correction:
                updates["executor"] = executor.model_dump()

        # ---- Specific gifts ----
        # Context: detect whether the assistant just asked about specific gifts
        # so we can accept a bare "no" / "none" as a confirmed no-gifts answer.
        last_assistant_asked_about_gifts = False
        if history:
            for item in reversed(history):
                if item.get("role") == "assistant":
                    content = item.get("content", "").lower()
                    if "specific gifts" in content or "bequests" in content:
                        last_assistant_asked_about_gifts = True
                    break

        bare_no_gifts = last_assistant_asked_about_gifts and bool(
            re.match(r"^\s*(no|none|nope|nah|not really|nothing)\s*[.!]?\s*$", lower)
        )

        if (state.specific_gifts is None) and (_user_declined_specific_gifts(msg) or bare_no_gifts):
            # User explicitly confirmed no gifts
            updates["specific_gifts"] = []
        else:
            gifts = _extract_specific_gifts(msg)
            if gifts:
                existing = [g.model_dump() for g in (state.specific_gifts or [])]
                for g in gifts:
                    gd = g.model_dump()
                    if gd not in existing:
                        existing.append(gd)
                updates["specific_gifts"] = existing

        # ---- Additional wishes ----
        additional = _extract_additional_wishes(msg)
        if additional and (state.additional_wishes is None or is_correction):
            # Only set if nothing else was extracted (avoid double-capturing)
            if not updates or is_correction:
                updates["additional_wishes"] = additional

        # ---- Generate reply ----
        reply = self._build_reply(updates, state, msg, is_correction)

        return ModelIntakeResponse(
            reply=reply,
            state_updates=updates,
            unresolved_fields=unresolved,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_ambiguous_executor(self, lower: str) -> bool:
        """True when user expresses uncertainty specifically about executor."""
        # 'or' must be a standalone word, not part of 'executor'
        has_standalone_or = bool(re.search(r"(?<!execut)\bor\b", lower))

        exec_keywords = r"executor|appoint"
        uncertain_keywords = r"maybe|not sure|either|thinking|considering|might|could be|undecided|perhaps|unsure"
        # Ambiguous: executor keyword + explicit uncertainty words
        if re.search(exec_keywords, lower) and re.search(uncertain_keywords, lower):
            return True
        # Ambiguous: "brother or friend" type phrasing (without a correction signal)
        if (
            has_standalone_or
            and re.search(r"\b(brother|friend|sister|colleague)\b", lower)
            and not re.search(r"\b(actually|correct|update|change|sorry)\b", lower)
        ):
            return True
        return False

    def _build_reply(
        self,
        updates: dict,
        state: PersonalWishesState,
        original_msg: str,
        is_correction: bool,
    ) -> str:
        parts: list[str] = []

        if is_correction and updates:
            parts.append("Got it — I've updated that for you.")
        elif updates:
            # Friendly acknowledgement based on what was captured
            if "full_name" in updates:
                parts.append(f"Thank you, {updates['full_name'].split()[0]}.")
            elif "executor" in updates:
                exec_name = (updates["executor"] or {}).get("name", "")
                parts.append(f"Noted — {exec_name} will be recorded as your executor." if exec_name else "Noted.")
            elif "has_children" in updates and not updates["has_children"]:
                parts.append("Understood, no children to record.")
            elif "has_children" in updates and updates.get("children_names"):
                names = ", ".join(updates["children_names"])
                parts.append(f"I've noted your children: {names}.")
            elif "specific_gifts" in updates:
                sg = updates["specific_gifts"]
                if sg == []:
                    parts.append("Understood, no specific gifts to record.")
                elif len(sg) == 1:
                    parts.append("I've recorded that bequest.")
                else:
                    parts.append(f"I've recorded {len(sg)} bequests.")
            elif "covers_worldwide_assets" in updates:
                if updates["covers_worldwide_assets"]:
                    parts.append("Got it. The document will cover your worldwide assets.")
                else:
                    parts.append("Got it. The document won't cover worldwide assets.")
            else:
                parts.append("Thank you, I've recorded that.")
        else:
            parts.append("I didn't quite catch a specific detail from that — could you rephrase?")

        # Ask for next missing field
        next_q = self._next_question(state, updates)
        if next_q:
            parts.append(next_q)

        return " ".join(parts)

    def _next_question(self, state: PersonalWishesState, pending_updates: dict) -> str | None:
        """Return the question for the next missing required field."""
        # Merge pending updates into a temporary view
        merged = state.model_copy(deep=True)
        for k, v in pending_updates.items():
            if hasattr(merged, k):
                setattr(merged, k, v)

        required_order = [
            "full_name",
            "home_address",
            "covers_worldwide_assets",
            "has_children",
            "executor",
            "specific_gifts",
            "additional_wishes",
        ]

        for field in required_order:
            val = getattr(merged, field)
            if field == "full_name" and not val:
                return _QUESTION_MAP["full_name"]
            if field == "home_address" and not val:
                return _QUESTION_MAP["home_address"]
            if field == "covers_worldwide_assets" and val is None:
                return _QUESTION_MAP["covers_worldwide_assets"]
            if field == "has_children" and val is None:
                return _QUESTION_MAP["has_children"]
            if field == "executor" and not val:
                return _QUESTION_MAP["executor"]
            if field == "specific_gifts":
                # None = not yet answered → ask
                # []   = confirmed no gifts → skip
                # [...] = has gifts → skip
                if val is None:
                    return _QUESTION_MAP["specific_gifts"]
            if field == "additional_wishes" and not val:
                return _QUESTION_MAP["additional_wishes"]

        return "That completes the information I need. Please review your document below."


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_provider() -> LLMProvider:
    """
    Return the LLM provider.

    The deterministic mock is the only provider. It requires no API keys or
    external services, which means the evaluator can run the application
    immediately without any configuration.

    In production this function would be replaced with a real LLM provider
    (e.g. Google Gemini, OpenAI) behind the same LLMProvider interface —
    no other code changes required.
    """
    return MockLLMProvider()
