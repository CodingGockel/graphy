from fastapi import APIRouter, Depends, Query, status
from src.models.schemas import ChatRequest, ChatResponse, ModelResponse, FullTableResponse
from src.services.chat_service import ChatService
from src.api.dependencies import get_chat_service
from src.api.responses import RESP_500, RESP_502, RESP_503

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
        "1. If no `session_id` is provided, a new session is created.\n"
        "2. Chat history is loaded from the database for the session.\n"
        "3. The LLM decides via tool calling whether to execute a new SPARQL query, "
        "reuse previous results, or ask a clarification question.\n"
        "4. The response includes a `session_id` to use for follow-up messages.\n\n"
        "**Response statuses:**\n"
        "- `200 OK`: Response generated successfully.\n"
        "- `503 Service Unavailable`: A dependent service (LLM or GraphDB) is unreachable.\n"
    ),
    operation_id="chat_process",
    responses={200: {"model": ChatResponse}, **ERROR_RESPONSES},
)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return await service.process(request)

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
