from unittest.mock import AsyncMock, MagicMock

from src.api.dependencies import get_chat_service
from src.main import app
from src.models.schemas import ModelResponse


def _override_chat_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    return service


class TestModelsEndpoint:
    def test_get_models(self, client):
        service = _override_chat_service()
        service.models = AsyncMock(return_value=ModelResponse(models={"a", "b"}))

        resp = client.get("/api/v1/models")

        assert resp.status_code == 200
        assert sorted(resp.json()["models"]) == ["a", "b"]

    def test_old_path_is_gone(self, client):
        _override_chat_service()
        assert client.get("/api/v1/chat/models").status_code == 404

