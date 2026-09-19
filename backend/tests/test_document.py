"""
Tests for the document generator.
"""
from backend.app.document_generator import generate_document
from backend.app.models import Executor, PersonalWishesState, SpecificGift


DISCLAIMER = "FICTIONAL — NOT LEGAL ADVICE"


class TestDocumentGenerator:
    def test_disclaimer_always_present(self):
        doc = generate_document(PersonalWishesState())
        assert DISCLAIMER in doc

    def test_empty_state_generates_document(self):
        doc = generate_document(PersonalWishesState())
        assert "PERSONAL WISHES DOCUMENT" in doc
        assert "Not yet provided" in doc

    def test_partial_state_shows_known_fields(self):
        state = PersonalWishesState(full_name="Jane Smith")
        doc = generate_document(state)
        assert "Jane Smith" in doc

    def test_complete_state_generates_document(self):
        state = PersonalWishesState(
            full_name="Jane Smith",
            home_address="12 Elm Street, London",
            covers_worldwide_assets=True,
            has_children=True,
            children_names=["Alice", "Ben"],
            executor=Executor(name="James Smith", relationship="brother"),
            specific_gifts=[SpecificGift(recipient="Alice", description="£10,000")],
            additional_wishes="Donate remaining belongings to charity.",
        )
        doc = generate_document(state)
        assert "Jane Smith" in doc
        assert "12 Elm Street, London" in doc
        assert "worldwide" in doc.lower()
        assert "Alice" in doc
        assert "Ben" in doc
        assert "James Smith" in doc
        assert "brother" in doc.lower()
        assert "£10,000" in doc
        assert "charity" in doc

    def test_no_children_shown_correctly(self):
        state = PersonalWishesState(has_children=False)
        doc = generate_document(state)
        assert "None" in doc

    def test_worldwide_assets_yes(self):
        state = PersonalWishesState(covers_worldwide_assets=True)
        doc = generate_document(state)
        assert "worldwide" in doc.lower()

    def test_worldwide_assets_no(self):
        state = PersonalWishesState(covers_worldwide_assets=False)
        doc = generate_document(state)
        assert "not worldwide" in doc

    def test_disclaimer_appears_twice(self):
        """Disclaimer at top and bottom of document."""
        doc = generate_document(PersonalWishesState())
        assert doc.count(DISCLAIMER) >= 1

    def test_specific_gifts_none_shows_not_yet_provided(self):
        """specific_gifts=None (unanswered) must show 'Not yet provided'."""
        state = PersonalWishesState()
        assert state.specific_gifts is None
        doc = generate_document(state)
        assert "Not yet provided" in doc

    def test_specific_gifts_empty_shows_none_specified(self):
        """specific_gifts=[] (confirmed no gifts) must show 'None specified.'"""
        state = PersonalWishesState(specific_gifts=[])
        doc = generate_document(state)
        assert "None specified." in doc
        assert "Not yet provided" not in doc.split("Specific Gifts:")[1].split("\n")[1]

    def test_specific_gifts_list_shows_each_gift(self):
        """specific_gifts with items must list them with description → recipient."""
        state = PersonalWishesState(
            specific_gifts=[
                SpecificGift(description="Laptop", recipient="Aarav"),
                SpecificGift(description="Watch", recipient="Anaya"),
            ]
        )
        doc = generate_document(state)
        assert "Laptop" in doc
        assert "Aarav" in doc
        assert "Watch" in doc
        assert "Anaya" in doc

