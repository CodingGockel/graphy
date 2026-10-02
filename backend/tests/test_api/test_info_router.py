from unittest.mock import AsyncMock, MagicMock

from src.api.dependencies import get_chat_service
from src.main import app
from src.models.schemas import FullTable, FullTableResponse, ModelResponse


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


class TestTableEndpoint:
    def test_get_table(self, client):
        service = _override_chat_service()
        service.get_full_table = AsyncMock(
            return_value=FullTableResponse(
                full_table=FullTable(columns=["name"], rows=[{"name": "Rose"}])
            )
        )

        resp = client.get("/api/v1/table?limit=5")

        assert resp.status_code == 200
        assert resp.json()["full_table"]["rows"] == [{"name": "Rose"}]
        service.get_full_table.assert_awaited_once_with(5)

    def test_invalid_limit_is_422(self, client):
        _override_chat_service()
        resp = client.get("/api/v1/table?limit=0")  # ge=1
        assert resp.status_code == 422

    def test_old_path_is_gone(self, client):
        _override_chat_service()
        assert client.get("/api/v1/chat/full_table").status_code == 404
