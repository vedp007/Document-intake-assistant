"""
Tests for PersonalWishesState schema and StateManager merge logic.
"""
import pytest
from pydantic import ValidationError

from backend.app.models import Executor, PersonalWishesState, SpecificGift
from backend.app.state_manager import StateManager


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestPersonalWishesState:
    def test_defaults_are_none(self):
        state = PersonalWishesState()
        assert state.full_name is None
        assert state.home_address is None
        assert state.covers_worldwide_assets is None
        assert state.has_children is None
        assert state.children_names == []
        assert state.executor is None
        assert state.specific_gifts is None  # None = not yet answered
        assert state.additional_wishes is None

    def test_executor_partial(self):
        """Executor must accept partial information (name only)."""
        e = Executor(name="James")
        assert e.name == "James"
        assert e.relationship is None

    def test_specific_gift_requires_both_fields(self):
        with pytest.raises(ValidationError):
            SpecificGift(recipient="Alice")  # missing description


# ---------------------------------------------------------------------------
# StateManager — merging
# ---------------------------------------------------------------------------

class TestStateManagerMerge:
    def setup_method(self):
        self.sm = StateManager()

    def test_merge_new_field(self):
        rejected = self.sm.apply_updates({"full_name": "Jane Smith"})
        assert self.sm.state.full_name == "Jane Smith"
        assert rejected == []

    def test_preserve_existing_fields(self):
        self.sm.apply_updates({"full_name": "Jane Smith", "home_address": "12 Elm St"})
        self.sm.apply_updates({"covers_worldwide_assets": True})
        # Previously set fields must not be clobbered
        assert self.sm.state.full_name == "Jane Smith"
        assert self.sm.state.home_address == "12 Elm St"
        assert self.sm.state.covers_worldwide_assets is True

    def test_correction_overwrites_existing(self):
        self.sm.apply_updates({"executor": {"name": "James Smith", "relationship": "brother"}})
        assert self.sm.state.executor.name == "James Smith"

        self.sm.apply_updates({"executor": {"name": "Sarah Smith", "relationship": "sister"}})
        assert self.sm.state.executor.name == "Sarah Smith"
        assert self.sm.state.executor.relationship == "sister"

    def test_invalid_field_rejected(self):
        rejected = self.sm.apply_updates({"nonexistent_field": "value"})
        assert "nonexistent_field" in rejected

    def test_invalid_executor_type_rejected(self):
        """A string instead of an object for executor should be rejected."""
        rejected = self.sm.apply_updates({"executor": "not-an-object"})
        assert "executor" in rejected
        assert self.sm.state.executor is None

    def test_boolean_coercion_valid_strings(self):
        """covers_worldwide_assets accepts 'true'/'false' strings from an LLM."""
        self.sm.apply_updates({"covers_worldwide_assets": "true"})
        assert self.sm.state.covers_worldwide_assets is True

        sm2 = StateManager()
        sm2.apply_updates({"covers_worldwide_assets": "false"})
        assert sm2.state.covers_worldwide_assets is False

    def test_specific_gifts_accumulated(self):
        gifts = [{"recipient": "Alice", "description": "\u00a310,000"}]
        self.sm.apply_updates({"specific_gifts": gifts})
        assert len(self.sm.state.specific_gifts) == 1
        assert self.sm.state.specific_gifts[0].recipient == "Alice"

    def test_specific_gifts_empty_list_is_valid(self):
        """specific_gifts=[] means confirmed no gifts — must be accepted and stored."""
        rejected = self.sm.apply_updates({"specific_gifts": []})
        assert rejected == []
        assert self.sm.state.specific_gifts == []

    def test_specific_gifts_none_is_valid(self):
        """specific_gifts=None means reset to unanswered — must be accepted."""
        self.sm.apply_updates({"specific_gifts": [{"recipient": "Alice", "description": "watch"}]})
        rejected = self.sm.apply_updates({"specific_gifts": None})
        assert rejected == []
        assert self.sm.state.specific_gifts is None

    def test_invalid_string_full_name_rejected(self):
        """full_name must be a str — integer must be rejected, not silently coerced."""
        rejected = self.sm.apply_updates({"full_name": 123})
        assert "full_name" in rejected
        assert self.sm.state.full_name is None  # state unchanged

    def test_invalid_string_home_address_rejected(self):
        """home_address must be a str — integer must be rejected."""
        rejected = self.sm.apply_updates({"home_address": 456})
        assert "home_address" in rejected
        assert self.sm.state.home_address is None  # state unchanged

    def test_invalid_boolean_string_rejected(self):
        """Arbitrary strings must NOT be silently coerced to boolean."""
        rejected = self.sm.apply_updates({"has_children": "banana"})
        assert "has_children" in rejected
        assert self.sm.state.has_children is None  # state unchanged

    def test_invalid_boolean_number_rejected(self):
        """Numeric values must NOT be silently coerced to boolean."""
        rejected = self.sm.apply_updates({"covers_worldwide_assets": 123})
        assert "covers_worldwide_assets" in rejected
        assert self.sm.state.covers_worldwide_assets is None  # state unchanged

    def test_children_names_non_string_rejected(self):
        """children_names lists containing non-strings must be rejected entirely."""
        rejected = self.sm.apply_updates({"children_names": ["Alice", 123]})
        assert "children_names" in rejected
        assert self.sm.state.children_names == []  # state unchanged


# ---------------------------------------------------------------------------
# StateManager — missing fields
# ---------------------------------------------------------------------------

class TestMissingFields:
    def test_all_missing_initially(self):
        sm = StateManager()
        missing = sm.get_missing_fields()
        assert "full_name" in missing
        assert "executor" in missing

    def test_children_names_required_when_has_children_true(self):
        sm = StateManager()
        sm.apply_updates({"has_children": True})
        assert "children_names" in sm.get_missing_fields()

    def test_children_names_not_required_when_no_children(self):
        sm = StateManager()
        sm.apply_updates({"has_children": False})
        assert "children_names" not in sm.get_missing_fields()

    def test_field_removed_from_missing_after_capture(self):
        sm = StateManager()
        sm.apply_updates({"full_name": "Jane Smith"})
        assert "full_name" not in sm.get_missing_fields()

    def test_specific_gifts_none_is_missing(self):
        """specific_gifts=None (initial default) must appear in missing fields."""
        sm = StateManager()
        assert "specific_gifts" in sm.get_missing_fields()

    def test_specific_gifts_empty_list_is_complete(self):
        """specific_gifts=[] (explicit no gifts) must NOT appear in missing fields."""
        sm = StateManager()
        sm.apply_updates({"specific_gifts": []})
        assert "specific_gifts" not in sm.get_missing_fields()

    def test_specific_gifts_with_items_is_complete(self):
        """specific_gifts with gifts must NOT appear in missing fields."""
        sm = StateManager()
        sm.apply_updates({"specific_gifts": [{"recipient": "Bob", "description": "watch"}]})
        assert "specific_gifts" not in sm.get_missing_fields()


# ---------------------------------------------------------------------------
# StateManager — manual edit
# ---------------------------------------------------------------------------

class TestManualEdit:
    def test_manual_edit_updates_field(self):
        sm = StateManager()
        sm.apply_manual_edit("full_name", "John Doe")
        assert sm.state.full_name == "John Doe"

    def test_manual_edit_unknown_field_raises(self):
        sm = StateManager()
        with pytest.raises(ValueError):
            sm.apply_manual_edit("unknown_field", "value")


# ---------------------------------------------------------------------------
# StateManager — reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_state_and_history(self):
        sm = StateManager()
        sm.apply_updates({"full_name": "Jane"})
        sm.add_message("user", "hello")
        sm.reset()
        assert sm.state.full_name is None
        assert sm.history == []
