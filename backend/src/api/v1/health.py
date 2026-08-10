from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from src.models.schemas import HealthResponse, ErrorResponse
from src.services.health_service import HealthService
from src.api.dependencies import get_health_service

router = APIRouter(prefix="/health", tags=["Health"])

@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check for the Data Explorer API",
    description=(
        "Returns the aggregated health status of all dependent services.\n\n"
        "**Overall status values:**\n"
        "- `ok`: All services are healthy and fully operational.\n"
        "- `degraded`: At least one service is partially available (e.g., a configured LLM model is not available).\n"
        "- `down`: At least one service is completely unavailable (e.g., LLM or GraphDB unreachable).\n\n"
        "**Monitored services:**\n"
        "- `sparql_service`: GraphDB SPARQL endpoint connectivity.\n"
        "- `llm_service`: LLM API (Blablador) availability and configured model presence.\n\n"
        "**Response statuses:**\n"
        "- `200 OK`: All services are healthy (status: 'ok').\n"
        "- `503 Service Unavailable`: At least one service is degraded or down. "
        "Check the `status` and `error` fields for details.\n"
    ),
    operation_id="health_check",
    responses={
        200: {
            "model": HealthResponse,
            "description": "All services are healthy.",
        },
        503: {
            "model": ErrorResponse,
            "description": "At least one service is degraded or down.",
        },
    },
)
async def health(service: HealthService = Depends(get_health_service)):
    result = await service.process()
    code = 200 if result.status == "ok" else 503
    return JSONResponse(status_code=code, content=result.model_dump())