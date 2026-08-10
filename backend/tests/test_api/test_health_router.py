from unittest.mock import AsyncMock, MagicMock

from src.api.dependencies import get_health_service
from src.main import app
from src.models.schemas import HealthResponse, ServiceHealth


def _override_health_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_health_service] = lambda: service
    return service


def _health(status: str) -> HealthResponse:
    return HealthResponse(
        status=status,
        services={
            "sparql_service": ServiceHealth(status="ok"),
            "llm_service": ServiceHealth(status=status if status != "ok" else "ok"),
        },
    )


class TestHealthEndpoint:
    def test_ok_returns_200(self, client):
        service = _override_health_service()
        service.process = AsyncMock(return_value=_health("ok"))

        resp = client.get("/api/v1/health/")

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_degraded_returns_503(self, client):
        service = _override_health_service()
        service.process = AsyncMock(return_value=_health("degraded"))

        resp = client.get("/api/v1/health/")

        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"

    def test_down_returns_503(self, client):
        service = _override_health_service()
        service.process = AsyncMock(return_value=_health("down"))

        resp = client.get("/api/v1/health/")

        assert resp.status_code == 503
