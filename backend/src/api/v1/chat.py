import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from src.db.repository import ChatRepository
from src.models.events import SSE_PING, ChatEvent, encode_sse
from src.models.schemas import ChatRequest, ModelResponse, FullTableResponse
from src.services.chat_service import ChatService, TurnState
from src.api.dependencies import get_chat_service, get_db_sessionmaker
from src.api.exception_handlers import stream_error_event
from src.api.responses import RESP_404, RESP_500, RESP_502, RESP_503
from src.util.exceptions import SessionNotFoundException
from src.util.logger import logger

router = APIRouter(prefix="/chat", tags=["Chat"])

ERROR_RESPONSES = {**RESP_502, **RESP_503, **RESP_500}

# Seconds without an event after which a `: ping` comment keeps the stream open.
PING_INTERVAL = 15.0

# The event loop only keeps weak references to tasks; a producer must not be
# collected while it still stores an aborted turn.
_producers: set[asyncio.Task[None]] = set()


async def _mark_aborted(sessionmaker, state: TurnState) -> None:
    """Store a turn the client walked away from, with what it had produced so far.
    Through a fresh DB session: the cancellation may have hit the run's own session
    in the middle of an operation, which leaves that connection unusable."""
    if state.message_id is None:
        return
    try:
        async with sessionmaker() as db:
            await ChatRepository(db).abort_message(
                state.message_id, content=state.answer, thinking=state.thinking or None
            )
    except Exception:
        logger.exception(f"Could not mark message {state.message_id} as aborted")


async def _produce(
    service: ChatService,
    sessionmaker,
    request: ChatRequest,
    queue: asyncio.Queue[ChatEvent | None],
    state: TurnState,
) -> None:
    """Run the turn and put its events on the queue; `None` marks the end. The DB
    session lives in here, for as long as the turn runs."""
    try:
        async with sessionmaker() as db:
            repo = ChatRepository(db)
            async for event in service.run(request.session_id, request.message, repo, state):
                await queue.put(event)
    except asyncio.CancelledError:
        # The client is gone. Shielded, so the cancellation cannot interrupt it.
        await asyncio.shield(_mark_aborted(sessionmaker, state))
        raise
    except Exception as exc:
        # The response has started: errors are reported in-band.
        await queue.put(stream_error_event(exc))
    await queue.put(None)


async def _stream(
    service: ChatService, sessionmaker, request: ChatRequest
) -> AsyncIterator[str]:
    """The response body: the turn's events as SSE frames, with a ping whenever
    nothing happened for PING_INTERVAL seconds."""
    queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue()
    producer = asyncio.create_task(_produce(service, sessionmaker, request, queue, TurnState()))
    _producers.add(producer)
    producer.add_done_callback(_producers.discard)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL)
            except asyncio.TimeoutError:
                yield SSE_PING
                continue
            if event is None:
                break
            yield encode_sse(event)
    finally:
        # Client disconnected (the generator is cancelled or closed) → stop the turn.
        # A no-op once the producer has finished.
        producer.cancel()


@router.post(
    "",
    response_class=StreamingResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with the Knowledge Graph",
    description=(
        "Processes a natural language question and streams the turn as Server-Sent "
        "Events (`text/event-stream`).\n\n"
        "**Flow:**\n"
        "1. If no `session_id` is provided, a new session is created; an unknown "
        "`session_id` is a 404 (as JSON, before the stream starts).\n"
        "2. Chat history is loaded from the database for the session.\n"
        "3. The LLM decides via tool calling whether to execute a new SPARQL query, "
        "reuse previous results, or ask a clarification question.\n\n"
        "**Events:** `session` → (`step_started` → `step_finished`)* → `answer` → `done`. "
        "The `session` event carries the `session_id` to use for follow-up messages. "
        "A failure after the stream has started arrives as an `error` event, which ends "
        "the stream. `: ping` comment lines keep an idle stream open.\n\n"
        "**Response statuses:**\n"
        "- `200 OK`: The stream has started.\n"
        "- `404 Not Found`: No session exists with the given `session_id`.\n"
    ),
    operation_id="chat_process",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "The turn as SSE."},
        **RESP_404,
        **RESP_500,
    },
)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    sessionmaker=Depends(get_db_sessionmaker),
) -> StreamingResponse:
    # The last point where a status code can still be chosen.
    if request.session_id is not None:
        async with sessionmaker() as db:
            if not await ChatRepository(db).session_exists(request.session_id):
                raise SessionNotFoundException(f"Session {request.session_id} not found")

    # The stream opens its own DB session: a yield-dependency would be closed before
    # the body is sent.
    return StreamingResponse(
        _stream(service, sessionmaker, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

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
    operation_id="chat_list_models",
    responses={200: {"model": ModelResponse}, **ERROR_RESPONSES},
)
async def models(service: ChatService = Depends(get_chat_service)) -> ModelResponse:
    return await service.models()

@router.get(
    "/full_table",
    response_model=FullTableResponse,
    status_code=status.HTTP_200_OK,
    summary="Returns the predefined full-table view",
    description=(
        "Runs a fixed, server-side SPARQL query (no LLM involved) and returns the result "
        "as a structured table.\n\n"
        "The columns are defined by the `full_table_columns` setting and the query by the "
        "`full_table_query_path` setting. The response nests `columns` (ordered) and `rows` "
        "(one object per row, keyed by column name; numeric cells are typed) under "
        "`full_table`.\n\n"
        "An optional `limit` query parameter caps the number of rows returned.\n\n"
        "**Response statuses:**\n"
        "- `200 OK`: Table returned successfully.\n"
        "- `503 Service Unavailable`: Could not reach the SPARQL endpoint. Check server logs for details.\n"
    ),
    operation_id="chat_full_table",
    responses={200: {"model": FullTableResponse}, **ERROR_RESPONSES},
)
async def full_table(
    limit: int | None = Query(
        default=None, ge=1, description="Maximum number of rows to return. No limit if omitted."
    ),
    service: ChatService = Depends(get_chat_service),
) -> FullTableResponse:
    return await service.get_full_table(limit)
