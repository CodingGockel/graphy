from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.models.schemas import SessionDetail, SessionRename, SessionSummary, StepResult
from src.services.session_service import SessionService
from src.api.dependencies import get_session_service
from src.api.responses import RESP_404, RESP_500

router = APIRouter(tags=["Sessions"])

ERROR_RESPONSES = {**RESP_404, **RESP_500}

# Upper bound of `ids` in one GET /sessions request.
MAX_SESSION_IDS = 100


def _parse_ids(ids: str) -> list[UUID]:
    """The comma-separated `ids` parameter as distinct UUIDs, in the given order."""
    try:
        parsed = list(dict.fromkeys(UUID(part.strip()) for part in ids.split(",") if part.strip()))
    except ValueError:
        raise HTTPException(status_code=422, detail="`ids` must be a comma-separated list of UUIDs")
    if not parsed:
        raise HTTPException(status_code=422, detail="`ids` must contain at least one ID")
    if len(parsed) > MAX_SESSION_IDS:
        raise HTTPException(
            status_code=422, detail=f"`ids` may contain at most {MAX_SESSION_IDS} IDs"
        )
    return parsed


@router.get(
    "/sessions",
    response_model=list[SessionSummary],
    status_code=status.HTTP_200_OK,
    summary="Metadata of the given sessions",
    description=(
        "Returns title, last update and message count for the sessions whose IDs are "
        "given in `ids` (comma-separated, at most 100), most recently updated first. "
        "Unknown IDs are simply left out.\n\n"
        "There is deliberately no way to list all sessions: without authentication "
        "every visitor would see every chat. A client keeps the IDs of its own sessions.\n\n"
        "- `200 OK`: Metadata returned (possibly an empty list).\n"
        "- `422 Unprocessable Entity`: `ids` is missing, empty, too long or not UUIDs.\n"
    ),
    operation_id="sessions_get",
    responses={200: {"model": list[SessionSummary]}, **RESP_500},
)
async def get_sessions(
    ids: str = Query(description="Comma-separated session IDs, at most 100."),
    service: SessionService = Depends(get_session_service),
) -> list[SessionSummary]:
    return await service.get_sessions(_parse_ids(ids))


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    status_code=status.HTTP_200_OK,
    summary="Get a session's full chat history",
    description=(
        "Returns the session with its complete chronological message history. Each "
        "assistant message carries the tool steps of its turn, without their results "
        "(see `GET /steps/{step_id}/result`).\n\n"
        "- `200 OK`: Session returned.\n"
        "- `404 Not Found`: No session exists with the given id.\n"
    ),
    operation_id="sessions_get_one",
    responses={200: {"model": SessionDetail}, **ERROR_RESPONSES},
)
async def get_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> SessionDetail:
    return await service.get_session(session_id)


@router.patch(
    "/sessions/{session_id}",
    response_model=SessionSummary,
    status_code=status.HTTP_200_OK,
    summary="Rename a session",
    description=(
        "Sets the session title. A title set this way counts as manual and is never "
        "overwritten by a generated one.\n\n"
        "- `200 OK`: Title set; the session's metadata is returned.\n"
        "- `404 Not Found`: No session exists with the given id.\n"
    ),
    operation_id="sessions_rename",
    responses={200: {"model": SessionSummary}, **ERROR_RESPONSES},
)
async def rename_session(
    session_id: UUID,
    body: SessionRename,
    service: SessionService = Depends(get_session_service),
) -> SessionSummary:
    return await service.rename_session(session_id, body.title)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session and its history",
    description=(
        "Deletes the session entirely; its messages and their steps are removed via cascade. The id "
        "becomes invalid afterwards.\n\n"
        "- `204 No Content`: Session deleted.\n"
        "- `404 Not Found`: No session exists with the given id.\n"
    ),
    operation_id="sessions_delete",
    responses=ERROR_RESPONSES, #type: ignore
)
async def delete_session(
    session_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> None:
    await service.delete_session(session_id)


@router.get(
    "/steps/{step_id}/result",
    response_model=StepResult,
    status_code=status.HTTP_200_OK,
    summary="Get the result of a tool step",
    description=(
        "Returns the stored result of one step: the SPARQL JSON of a query, the "
        "candidates of an entity lookup, `null` for a step that has none. Results are "
        "never part of the chat stream or the session history; a client loads them "
        "when it shows a step.\n\n"
        "- `200 OK`: Result returned.\n"
        "- `404 Not Found`: No step exists with the given id.\n"
    ),
    operation_id="steps_get_result",
    responses={200: {"model": StepResult}, **ERROR_RESPONSES},
)
async def get_step_result(
    step_id: UUID,
    service: SessionService = Depends(get_session_service),
) -> StepResult:
    return await service.get_step_result(step_id)
