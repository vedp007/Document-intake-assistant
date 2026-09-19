"""
State manager for the Document Intake Assistant.

Responsibilities:
  - Maintain in-memory PersonalWishesState and conversation history.
  - Validate ModelIntakeResponse.state_updates before applying them.
  - Determine which required fields are still missing.
  - Apply manual field edits from the UI.
  - Reset the session.

Important: raw LLM output (state_updates dict) is always validated through
Pydantic before any mutation of the live state.
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .models import Executor, PersonalWishesState, SpecificGift


REQUIRED_FIELDS = [
    "full_name",
    "home_address",
    "covers_worldwide_assets",
    "has_children",
    "executor",
    "specific_gifts",
    "additional_wishes",
]


class StateManager:
    def __init__(self) -> None:
        self.state = PersonalWishesState()
        self.history: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # State mutation
    # ------------------------------------------------------------------

    def apply_updates(self, updates: dict[str, Any]) -> list[str]:
        """
        Validate and merge a dict of field deltas into the live state.

        Returns a list of field names that were rejected due to validation
        errors (so the caller can log / surface them without crashing).
        """
        rejected: list[str] = []

        for field, value in updates.items():
            if not hasattr(self.state, field):
                # Unknown field — ignore silently (LLM hallucination guard)
                rejected.append(field)
                continue

            try:
                self._set_field(field, value)
            except (ValidationError, ValueError, TypeError) as exc:
                rejected.append(field)
                # Non-fatal — continue with remaining fields

        return rejected

    def _set_field(self, field: str, value: Any) -> None:
        """Set a single validated field on the live state."""
        if field == "executor":
            if value is None:
                self.state.executor = None
            else:
                # Validate through Pydantic
                self.state.executor = Executor.model_validate(value)

        elif field == "specific_gifts":
            if value is None:
                self.state.specific_gifts = None
            elif not isinstance(value, list):
                raise ValueError("specific_gifts must be a list")
            else:
                self.state.specific_gifts = [
                    SpecificGift.model_validate(g) for g in value
                ]

        elif field == "children_names":
            if not isinstance(value, list):
                raise ValueError("children_names must be a list")
            if not all(isinstance(n, str) for n in value):
                raise ValueError("children_names must contain strings only")
            self.state.children_names = value

        elif field == "covers_worldwide_assets":
            value = self._coerce_bool(field, value)
            self.state.covers_worldwide_assets = value

        elif field == "has_children":
            value = self._coerce_bool(field, value)
            self.state.has_children = value

        else:
            # All remaining fields are str | None — reject non-str values
            if value is not None and not isinstance(value, str):
                raise ValueError(
                    f"{field!r}: expected str or None, got {type(value).__name__!r}"
                )
            setattr(self.state, field, value)

    @staticmethod
    def _coerce_bool(field: str, value: Any) -> bool | None:
        """
        Strict boolean coercion.

        Accepts:
          - Python bool (True / False)
          - Strings "true", "yes", "1"  → True
          - Strings "false", "no", "0" → False
          - None                        → None (field not yet known)

        Raises ValueError for anything else — e.g. "banana", 123, [].
        This ensures LLM garbage is rejected rather than silently coerced.
        """
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1"}:
                return True
            if normalized in {"false", "no", "0"}:
                return False
            raise ValueError(
                f"{field!r}: invalid boolean string {value!r}. "
                "Expected 'true'/'yes'/'1' or 'false'/'no'/'0'."
            )
        raise ValueError(
            f"{field!r}: expected bool or bool-like string, got {type(value).__name__!r}"
        )

    def apply_manual_edit(self, field: str, value: Any) -> None:
        """
        Apply a direct user edit from the UI.

        Raises ValueError for unknown fields and re-raises Pydantic
        ValidationError for type mismatches so the API layer can return
        a 422 response.
        """
        if not hasattr(self.state, field):
            raise ValueError(f"Unknown field: {field!r}")
        self._set_field(field, value)

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history."""
        self.history.append({"role": role, "content": content})

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_missing_fields(self) -> list[str]:
        """Return required fields that have not yet been captured."""
        missing: list[str] = []
        for field in REQUIRED_FIELDS:
            val = getattr(self.state, field)
            if field == "specific_gifts":
                # None  = user has not answered yet      → missing
                # []    = user confirmed no gifts         → complete
                # [...] = user provided gifts             → complete
                if val is None:
                    missing.append(field)
            elif field == "has_children":
                if val is None:
                    missing.append(field)
                elif val is True and not self.state.children_names:
                    missing.append("children_names")
            elif val is None or val == [] or val == "":
                missing.append(field)
        return missing

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Clear all state and history, starting a fresh session."""
        self.state = PersonalWishesState()
        self.history = []
