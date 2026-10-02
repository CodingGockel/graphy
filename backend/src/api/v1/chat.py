from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from src.db.repository import ChatRepository
from src.models.events import AnswerEvent, SessionEvent, StepFinishedEvent, StepStartedEvent
from src.models.schemas import ChatRequest, ChatResponse, ModelResponse, FullTableResponse
from src.services.chat_service import ChatService, TurnState
from src.api.dependencies import get_chat_service, get_db_sessionmaker
from src.util.sparql_utils import results_to_text
from src.api.responses import RESP_404, RESP_500, RESP_502, RESP_503

router = APIRouter(prefix="/chat", tags=["Chat"])

ERROR_RESPONSES = {**RESP_502, **RESP_503, **RESP_500}

@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with the Knowledge Graph",
    description=(
        "Processes a natural language question and returns a structured response.\n\n"
        "**Flow:**\n"
        "1. If no `session_id` is provided, a new session is created; an unknown "
        "`session_id` is a 404.\n"
        "2. Chat history is loaded from the database for the session.\n"
        "3. The LLM decides via tool calling whether to execute a new SPARQL query, "
        "reuse previous results, or ask a clarification question.\n"
        "4. The response includes a `session_id` to use for follow-up messages.\n\n"
        "**Response statuses:**\n"
        "- `200 OK`: Response generated successfully.\n"
        "- `404 Not Found`: No session exists with the given `session_id`.\n"
        "- `503 Service Unavailable`: A dependent service (LLM or GraphDB) is unreachable.\n"
    ),
    operation_id="chat_process",
    responses={200: {"model": ChatResponse}, **RESP_404, **ERROR_RESPONSES},
)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
    sessionmaker=Depends(get_db_sessionmaker),
) -> ChatResponse:
    # Temporary adapter (replaced by the SSE route): consume the event stream of the
    # turn and assemble the old one-shot response from it.
    async with sessionmaker() as db:
        repo = ChatRepository(db)
        session_id: UUID | None = None
        answer = ""
        queries: dict[UUID, str] = {}
        last_query_step: UUID | None = None

        async for event in service.run(request.session_id, request.message, repo, TurnState()):
            if isinstance(event, SessionEvent):
                session_id = event.session_id
            elif isinstance(event, AnswerEvent):
                answer += event.delta
            elif isinstance(event, StepStartedEvent) and event.kind == "sparql_query":
                queries[event.step_id] = event.args.get("query", "")
            elif isinstance(event, StepFinishedEvent) and event.ok and event.step_id in queries:
                last_query_step = event.step_id

        # Query and result of the turn's last successful query step, read back
        # from the DB (results are not part of the events).
        query = ""
        result: str | None = None
        if last_query_step is not None:
            query = queries[last_query_step]
            stored = await repo.get_step_result(last_query_step)
            if stored is not None and stored[1] is not None:
                result = results_to_text(stored[1])

    assert session_id is not None  # `session` is always the first event
    return ChatResponse(
        answer=answer,
        session_id=session_id,
        llm_generated_query=query,
        sparql_query_result=result,
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
