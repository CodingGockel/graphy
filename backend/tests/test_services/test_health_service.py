from unittest.mock import AsyncMock, MagicMock

from src.models.schemas import ServiceHealth
from src.services.health_service import HealthService


def _make_service(sparql_health: ServiceHealth, llm_health: ServiceHealth):
    sparql = MagicMock()
    sparql.health_check = AsyncMock(return_value=sparql_health)
    llm = MagicMock()
    llm.health_check = AsyncMock(return_value=llm_health)
    return HealthService(llm=llm, sparql=sparql)


class TestProcess:
    async def test_all_ok(self):
        service = _make_service(ServiceHealth(status="ok"), ServiceHealth(status="ok"))
        result = await service.process()
        assert result.status == "ok"
        assert result.error is None
        assert set(result.services) == {"sparql_service", "llm_service"}

    async def test_any_degraded_is_degraded(self):
        service = _make_service(
            ServiceHealth(status="ok"),
            ServiceHealth(status="degraded", error="missing model"),
        )
        result = await service.process()
        assert result.status == "degraded"
        assert "llm_service: missing model" in result.error

    async def test_any_down_is_down(self):
        service = _make_service(
            ServiceHealth(status="down", error="unreachable"),
            ServiceHealth(status="degraded", error="missing model"),
        )
        result = await service.process()
        assert result.status == "down"

    async def test_errors_are_concatenated(self):
        service = _make_service(
            ServiceHealth(status="down", error="sparql err"),
            ServiceHealth(status="down", error="llm err"),
        )
        result = await service.process()
        assert "sparql_service: sparql err" in result.error
        assert "llm_service: llm err" in result.error
        assert "; " in result.error
