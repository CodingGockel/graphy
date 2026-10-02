from fastapi import APIRouter, Depends, status

from src.models.schemas import ModelResponse
from src.services.chat_service import ChatService
from src.api.dependencies import get_chat_service
from src.api.responses import RESP_500, RESP_502, RESP_503

router = APIRouter(tags=["Info"])

ERROR_RESPONSES = {**RESP_502, **RESP_503, **RESP_500}


@router.get(
    "/models",
    response_model=ModelResponse,
    status_code=status.HTTP_200_OK,
    summary="List available LLM models",
    description=(
        "Returns all model IDs available on the configured LLM API (Blablador).\n\n"
        "This helps verify which models are accessible and whether the configured "
        "`blablador_sparql_model` is available.\n\n"
        "**Response statuses:**\n"
        "- `200 OK`: Models returned successfully.\n"
        "- `503 Service Unavailable`: Could not reach the LLM API. Check server logs for details.\n"
    ),
    operation_id="list_models",
    responses={200: {"model": ModelResponse}, **ERROR_RESPONSES},
)
async def models(service: ChatService = Depends(get_chat_service)) -> ModelResponse:
    return await service.models()
