import asyncio
from src.services.llm_service import LLMService
from src.services.sparql_service import SparqlService
from src.models.schemas import HealthResponse, ServiceHealth, Status


class HealthService:
    def __init__(self, llm: LLMService, sparql: SparqlService):
        self.llm = llm
        self.sparql = sparql

    async def process(self) -> HealthResponse:
        sparql_health, llm_health = await asyncio.gather(
            self.sparql.health_check(),
            self.llm.health_check(),
        )
        services: dict[str, ServiceHealth] = {
            "sparql_service": sparql_health,
            "llm_service": llm_health,
        }

        if any(s.status == "down" for s in services.values()):
            status: Status = "down"
        elif any(s.status == "degraded" for s in services.values()):
            status = "degraded"
        else:
            status = "ok"

        errors = [f"{name}: {svc.error}" for name, svc in services.items() if svc.error]
        return HealthResponse(
            status=status,
            error="; ".join(errors) if errors else None,
            services=services,
        )
