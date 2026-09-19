"""
Tests for the MockLLMProvider — covers all 7 intake scenarios.
"""
import pytest

from backend.app.llm import MockLLMProvider
from backend.app.models import PersonalWishesState


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
def empty_state():
    return PersonalWishesState()


async def call(mock_llm, state, message):
    return await mock_llm.process_turn(history=[], state=state, user_message=message)


# ---------------------------------------------------------------------------
# Scenario A — Single field
# ---------------------------------------------------------------------------

class TestSingleFieldExtraction:
    @pytest.mark.asyncio
    async def test_extracts_name(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "My name is Jane Smith.")
        assert resp.state_updates.get("full_name") == "Jane Smith"

    @pytest.mark.asyncio
    async def test_no_spurious_updates_from_unrelated_message(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "What is this form for?")
        # Address, assets, executor etc. should NOT be fabricated
        assert "home_address" not in resp.state_updates
        assert "covers_worldwide_assets" not in resp.state_updates
        assert "executor" not in resp.state_updates

    @pytest.mark.asyncio
    async def test_accepts_bare_address_when_prompted(self, mock_llm, empty_state):
        """When the assistant just asked for the home address, accept any valid text."""
        empty_state.full_name = "Ved Patil"
        history = [
            {"role": "user", "content": "Ved Patil"},
            {"role": "assistant", "content": "Thank you, Ved. What is your home address?"},
        ]
        resp = await mock_llm.process_turn(
            history=history, state=empty_state, user_message="silver brook abvdhan"
        )
        assert resp.state_updates.get("home_address") == "silver brook abvdhan"

    @pytest.mark.asyncio
    async def test_accepts_flat_format_address_when_prompted(self, mock_llm, empty_state):
        """Indian flat-style address is accepted verbatim when prompted."""
        empty_state.full_name = "Ved Patil"
        history = [
            {"role": "user", "content": "Ved Patil"},
            {"role": "assistant", "content": "Thank you, Ved. What is your home address?"},
        ]
        resp = await mock_llm.process_turn(
            history=history, state=empty_state,
            user_message="flat b602, silver brook, bavdhan, pune"
        )
        assert "silver brook" in resp.state_updates.get("home_address", "").lower()

    @pytest.mark.asyncio
    async def test_accepts_international_addresses_when_prompted(self, mock_llm, empty_state):
        """Various international address formats are all accepted when prompted."""
        empty_state.full_name = "Test User"
        addresses = [
            "MG Road, Bengaluru, Karnataka, India",
            "12-3 Shibuya, Tokyo, Japan",
            "1600 Pennsylvania Avenue NW, Washington DC 20500",
        ]
        history = [
            {"role": "user", "content": "Test User"},
            {"role": "assistant", "content": "What is your home address?"},
        ]
        for addr in addresses:
            state = empty_state.model_copy()
            state.full_name = "Test User"
            resp = await mock_llm.process_turn(history=history, state=state, user_message=addr)
            assert resp.state_updates.get("home_address") == addr, f"Failed for: {addr}"


# ---------------------------------------------------------------------------
# Scenario B — Multiple fields in one message
# ---------------------------------------------------------------------------

class TestMultiFieldExtraction:
    @pytest.mark.asyncio
    async def test_name_and_address(self, mock_llm, empty_state):
        """Explicit 'I live at' phrase extracts address alongside name in one message."""
        resp = await call(
            mock_llm, empty_state,
            "I'm Jane Smith and I live at 12 Elm Street, London."
        )
        assert resp.state_updates.get("full_name") == "Jane Smith"
        assert resp.state_updates.get("home_address") is not None
        assert "Elm Street" in resp.state_updates.get("home_address", "")

    @pytest.mark.asyncio
    async def test_name_address_and_worldwide(self, mock_llm, empty_state):
        resp = await call(
            mock_llm, empty_state,
            "I'm Jane Smith, I live at 12 Elm Street, London and my assets are worldwide."
        )
        assert resp.state_updates.get("full_name") == "Jane Smith"
        assert resp.state_updates.get("covers_worldwide_assets") is True


# ---------------------------------------------------------------------------
# Scenario C — No children
# ---------------------------------------------------------------------------

class TestNoChildren:
    @pytest.mark.asyncio
    async def test_no_children_explicit(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "I don't have any children.")
        assert resp.state_updates.get("has_children") is False
        assert resp.state_updates.get("children_names", []) == []

    @pytest.mark.asyncio
    async def test_no_kids(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "No kids.")
        assert resp.state_updates.get("has_children") is False


# ---------------------------------------------------------------------------
# Scenario D — Children with names
# ---------------------------------------------------------------------------

class TestChildrenWithNames:
    @pytest.mark.asyncio
    async def test_two_children(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "I have two children, Alice and Ben.")
        assert resp.state_updates.get("has_children") is True
        names = resp.state_updates.get("children_names", [])
        assert "Alice" in names
        assert "Ben" in names


# ---------------------------------------------------------------------------
# Scenario E — Executor with relationship
# ---------------------------------------------------------------------------

class TestExecutorExtraction:
    @pytest.mark.asyncio
    async def test_executor_with_relationship(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "My brother James Smith should be my executor.")
        exec_data = resp.state_updates.get("executor", {})
        assert exec_data.get("name") == "James Smith"
        assert exec_data.get("relationship") == "brother"

    @pytest.mark.asyncio
    async def test_executor_name_only(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state, "My executor is James.")
        exec_data = resp.state_updates.get("executor", {})
        assert exec_data.get("name") is not None


# ---------------------------------------------------------------------------
# Scenario F — Ambiguity (no state update)
# ---------------------------------------------------------------------------

class TestAmbiguousInput:
    @pytest.mark.asyncio
    async def test_ambiguous_executor_no_update(self, mock_llm, empty_state):
        resp = await call(mock_llm, empty_state,
                         "I'm thinking about either my brother or my friend as executor.")
        # State must NOT be updated when user is undecided
        assert resp.state_updates == {}
        assert "executor" in resp.unresolved_fields
        # Reply should ask for clarification
        assert len(resp.reply) > 0


# ---------------------------------------------------------------------------
# Scenario G — Correction
# ---------------------------------------------------------------------------

class TestCorrection:
    @pytest.mark.asyncio
    async def test_executor_correction(self, mock_llm):
        state = PersonalWishesState(
            executor={"name": "James Smith", "relationship": "brother"}  # type: ignore[arg-type]
        )
        resp = await call(
            mock_llm, state,
            "Actually, my executor should be my sister Emma Smith."
        )
        exec_data = resp.state_updates.get("executor", {})
        assert exec_data.get("name") is not None
        assert "Emma" in exec_data.get("name", "")
        assert exec_data.get("relationship") == "sister"


# ---------------------------------------------------------------------------
# Scenario H — Contradiction
# ---------------------------------------------------------------------------

class TestContradiction:
    @pytest.mark.asyncio
    async def test_contradiction_child_mention_after_no_children(self, mock_llm):
        """If user said no children but now mentions a daughter, state must NOT update."""
        state = PersonalWishesState(has_children=False)
        resp = await call(
            mock_llm, state,
            "My daughter Alice should receive my watch."
        )
        # No state update — contradiction detected
        assert resp.state_updates == {}
        # Clarification fields must be flagged as unresolved
        assert "has_children" in resp.unresolved_fields


# ---------------------------------------------------------------------------
# Scenario I — Multiple specific gifts
# ---------------------------------------------------------------------------

class TestMultipleSpecificGifts:
    @pytest.mark.asyncio
    async def test_two_gifts_in_one_message(self, mock_llm, empty_state):
        """'give laptop to Aarav and watch to Anaya' must produce two separate gifts."""
        resp = await call(
            mock_llm, empty_state,
            "I want to give my laptop to Aarav and my watch to Anaya."
        )
        gifts = resp.state_updates.get("specific_gifts", [])
        assert len(gifts) == 2, f"Expected 2 gifts, got {len(gifts)}: {gifts}"
        descriptions = [g["description"].lower() for g in gifts]
        recipients = [g["recipient"] for g in gifts]
        assert any("laptop" in d for d in descriptions), f"Missing laptop in {descriptions}"
        assert any("watch" in d for d in descriptions), f"Missing watch in {descriptions}"
        assert "Aarav" in recipients, f"Missing Aarav in {recipients}"
        assert "Anaya" in recipients, f"Missing Anaya in {recipients}"

    @pytest.mark.asyncio
    async def test_single_gift(self, mock_llm, empty_state):
        """Single gift is still extracted correctly."""
        resp = await call(
            mock_llm, empty_state,
            "I want to give my watch to Aarav."
        )
        gifts = resp.state_updates.get("specific_gifts", [])
        assert len(gifts) == 1
        assert gifts[0]["description"].lower() == "watch"
        assert gifts[0]["recipient"] == "Aarav"


# ---------------------------------------------------------------------------
# Scenario J — No specific gifts
# ---------------------------------------------------------------------------

class TestNoSpecificGifts:
    @pytest.mark.asyncio
    async def test_explicit_no_gifts_phrase(self, mock_llm, empty_state):
        """'No specific gifts.' must produce specific_gifts=[]."""
        resp = await call(mock_llm, empty_state, "No specific gifts.")
        assert resp.state_updates.get("specific_gifts") == []

    @pytest.mark.asyncio
    async def test_no_gifts_i_have_none(self, mock_llm, empty_state):
        """'I don't have any specific gifts.' must produce specific_gifts=[]."""
        resp = await call(mock_llm, empty_state, "I don't have any specific gifts.")
        assert resp.state_updates.get("specific_gifts") == []

    @pytest.mark.asyncio
    async def test_bare_none_in_gifts_context(self, mock_llm, empty_state):
        """Bare 'None' when assistant just asked about gifts must produce specific_gifts=[]."""
        history = [
            {"role": "assistant", "content": "Do you have any specific gifts or bequests?"},
        ]
        resp = await mock_llm.process_turn(
            history=history, state=empty_state, user_message="None."
        )
        assert resp.state_updates.get("specific_gifts") == []

    @pytest.mark.asyncio
    async def test_bare_no_in_gifts_context(self, mock_llm, empty_state):
        """Bare 'no' when assistant just asked about gifts must produce specific_gifts=[]."""
        history = [
            {"role": "assistant", "content": "Do you have any specific gifts or bequests?"},
        ]
        resp = await mock_llm.process_turn(
            history=history, state=empty_state, user_message="no"
        )
        assert resp.state_updates.get("specific_gifts") == []

