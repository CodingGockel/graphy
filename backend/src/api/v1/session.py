from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.models.schemas import HistoryResponse, HistoryUpload
from src.services.session_service import SessionService
from src.api.dependencies import get_session_service
from src.api.responses import RESP_404, RESP_500

router = APIRouter(prefix="/session", tags=["Session"])

ERROR_RESPONSES = {**RESP_404, **RESP_500}


@router.get(
    "/{session_id}/history",
    response_model=HistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a session's full chat history",
    description=(
        "Returns the complete chronological message history stored for the session, "
        "including SPARQL queries and raw results so the frontend can rebuild the full "
        "chat and data views.\n\n"
        "- `200 OK`: History returned.\n"
        "- `404 Not Found`: No session exists with the given id.\n"
    ),
    operation_id="session_get_history",
    responses={200: {"model": HistoryResponse}, **ERROR_RESPONSES},
)
async def get_history(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> HistoryResponse:
    return await service.get_history(session_id)


@router.put(
    "/{session_id}/history",
    response_model=HistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Replace (upload) a session's chat history",
    description=(
        "Replaces the session's entire message history with the uploaded messages. "
        "If no session exists with the given id, it is created. Message order is "
        "preserved as given; `created_at` values in the payload are ignored.\n\n"
        "- `200 OK`: History stored; the resulting state is returned.\n"
    ),
    operation_id="session_replace_history",
    responses={200: {"model": HistoryResponse}, **ERROR_RESPONSES},
)
async def replace_history(
    session_id: UUID,
    upload: HistoryUpload,
    service: SessionService = Depends(get_session_service),
) -> HistoryResponse:
    return await service.replace_history(session_id, upload)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session and its history",
    description=(
        "Deletes the session entirely; its messages are removed via cascade. The id "
        "becomes invalid afterwards.\n\n"
        "- `204 No Content`: Session deleted.\n"
        "- `404 Not Found`: No session exists with the given id.\n"
    ),
    operation_id="session_delete",
    responses=ERROR_RESPONSES, #type: ignore
)
async def delete_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> None:
    await service.delete_session(session_id)
