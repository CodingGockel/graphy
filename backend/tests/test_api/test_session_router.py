import uuid
from unittest.mock import AsyncMock, MagicMock

from src.api.dependencies import get_session_service
from src.main import app
from src.models.schemas import HistoryMessage, HistoryResponse
from src.util.exceptions import SessionNotFoundException


def _override_session_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_session_service] = lambda: service
    return service


class TestGetHistory:
    def test_returns_history(self, client):
        service = _override_session_service()
        sid = uuid.uuid4()
        service.get_history = AsyncMock(
            return_value=HistoryResponse(
                session_id=sid,
                messages=[HistoryMessage(role="user", content="hi")],
            )
        )

        resp = client.get(f"/api/v1/session/{sid}/history")

        assert resp.status_code == 200
        assert resp.json()["messages"][0]["content"] == "hi"

    def test_not_found_is_404(self, client):
        service = _override_session_service()
        service.get_history = AsyncMock(side_effect=SessionNotFoundException("nope"))

        resp = client.get(f"/api/v1/session/{uuid.uuid4()}/history")

        assert resp.status_code == 404


class TestReplaceHistoryRemoved:
    def test_put_history_is_gone(self, client):
        _override_session_service()

        resp = client.put(
            f"/api/v1/session/{uuid.uuid4()}/history",
            json={"messages": [{"role": "user", "content": "new"}]},
        )

        assert resp.status_code == 405


class TestDeleteSession:
    def test_delete_returns_204(self, client):
        service = _override_session_service()
        service.delete_session = AsyncMock(return_value=None)

        resp = client.delete(f"/api/v1/session/{uuid.uuid4()}")

        assert resp.status_code == 204

    def test_delete_missing_is_404(self, client):
        service = _override_session_service()
        service.delete_session = AsyncMock(
            side_effect=SessionNotFoundException("nope")
        )

        resp = client.delete(f"/api/v1/session/{uuid.uuid4()}")

        assert resp.status_code == 404
