import uuid
from unittest.mock import AsyncMock, MagicMock

from src.api.dependencies import get_chat_service
from src.main import app
from src.models.schemas import ChatResponse, FullTable, FullTableResponse, ModelResponse


def _override_chat_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    return service


class TestChatEndpoint:
    def test_post_chat_returns_answer(self, client):
        service = _override_chat_service()
        sid = uuid.uuid4()
        service.process = AsyncMock(
            return_value=ChatResponse(answer="hello back", session_id=sid)
        )

        resp = client.post("/api/v1/chat/", json={"message": "hello"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"] == "hello back"
        assert body["session_id"] == str(sid)

    def test_post_chat_missing_message_is_422(self, client):
        _override_chat_service()
        resp = client.post("/api/v1/chat/", json={})
        assert resp.status_code == 422


class TestModelsEndpoint:
    def test_get_models(self, client):
        service = _override_chat_service()
        service.models = AsyncMock(return_value=ModelResponse(models={"a", "b"}))

        resp = client.get("/api/v1/chat/models")

        assert resp.status_code == 200
        assert sorted(resp.json()["models"]) == ["a", "b"]


class TestFullTableEndpoint:
    def test_get_full_table(self, client):
        service = _override_chat_service()
        service.get_full_table = AsyncMock(
            return_value=FullTableResponse(
                full_table=FullTable(columns=["name"], rows=[{"name": "Rose"}])
            )
        )

        resp = client.get("/api/v1/chat/full_table?limit=5")

        assert resp.status_code == 200
        assert resp.json()["full_table"]["rows"] == [{"name": "Rose"}]
        service.get_full_table.assert_awaited_once_with(5)

    def test_invalid_limit_is_422(self, client):
        _override_chat_service()
        resp = client.get("/api/v1/chat/full_table?limit=0")  # ge=1
        assert resp.status_code == 422
