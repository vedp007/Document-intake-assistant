"""
Integration tests for the /api/chat and /api/reset endpoints.
Uses FastAPI TestClient (synchronous) to test the full request pipeline.
"""
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app, _manager


@pytest.fixture(autouse=True)
def reset_between_tests():
    """Ensure a clean state for every test."""
    _manager.reset()
    yield
    _manager.reset()


client = TestClient(app)


class TestChatEndpoint:
    def test_chat_returns_reply_state_document(self):
        resp = client.post("/api/chat", json={"message": "My name is Jane Smith."})
        assert resp.status_code == 200
        body = resp.json()
        assert "reply" in body
        assert "state" in body
        assert "document" in body

    def test_chat_updates_state(self):
        client.post("/api/chat", json={"message": "My name is Jane Smith."})
        state_resp = client.get("/api/state")
        assert state_resp.json()["state"]["full_name"] == "Jane Smith"

    def test_chat_empty_message_rejected(self):
        resp = client.post("/api/chat", json={"message": "   "})
        assert resp.status_code == 422

    def test_chat_graceful_on_bad_input(self):
        """Non-extractable messages should not crash the server."""
        resp = client.post("/api/chat", json={"message": "asdfghjkl"})
        assert resp.status_code == 200
        assert "reply" in resp.json()

    def test_multi_turn_preserves_earlier_fields(self):
        client.post("/api/chat", json={"message": "My name is Jane Smith."})
        client.post("/api/chat", json={"message": "I don't have any children."})
        state = client.get("/api/state").json()["state"]
        # Both turns should be preserved
        assert state["full_name"] == "Jane Smith"
        assert state["has_children"] is False

    def test_chat_response_includes_missing_fields(self):
        """Chat response must include missing_fields so the frontend
        doesn't need a separate GET /api/state round-trip."""
        resp = client.post("/api/chat", json={"message": "My name is Jane Smith."})
        assert resp.status_code == 200
        body = resp.json()
        assert "missing_fields" in body
        # full_name is now captured, so it should not be in missing
        assert "full_name" not in body["missing_fields"]


class TestManualEdit:
    def test_manual_edit_field(self):
        resp = client.post(
            "/api/state/manual-edit",
            json={"field": "full_name", "value": "Alice Brown"}
        )
        assert resp.status_code == 200
        assert resp.json()["state"]["full_name"] == "Alice Brown"

    def test_manual_edit_unknown_field_422(self):
        resp = client.post(
            "/api/state/manual-edit",
            json={"field": "magic_field", "value": "something"}
        )
        assert resp.status_code == 422

    def test_manual_edit_document_reflects_change(self):
        """After a manual edit, the document endpoint must return the updated value."""
        client.post(
            "/api/state/manual-edit",
            json={"field": "full_name", "value": "Alice Brown"}
        )
        doc_resp = client.get("/api/document")
        assert doc_resp.status_code == 200
        assert "Alice Brown" in doc_resp.json()["document"]


class TestReset:
    def test_reset_clears_state(self):
        client.post("/api/chat", json={"message": "My name is Jane Smith."})
        client.post("/api/reset")
        state = client.get("/api/state").json()["state"]
        assert state["full_name"] is None
