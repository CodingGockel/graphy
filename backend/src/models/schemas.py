from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated, Optional, Literal, Any

Status = Literal["ok", "degraded", "down"]
MessageStatus = Literal["running", "complete", "aborted", "error"]

class ChatRequest(BaseModel):
    message: str = Field(
        description="Natural language question or request about the knowledge graph. "
        "The LLM will generate a SPARQL query to answer it."
    )
    session_id: UUID | None = Field(
        default=None,
        description="Session ID for conversation continuity. "
        "If null, a new session is created and its ID is sent in the `session` event."
    )


class SessionSummary(BaseModel):
    id: UUID = Field(
        description="Session ID."
    )
    title: str | None = Field(
        description="Session title; null as long as the session has none."
    )
    updated_at: datetime = Field(
        description="When the last turn of the session completed (creation time before that)."
    )
    message_count: int = Field(
        description="Number of stored messages (user and assistant)."
    )


class StepOut(BaseModel):
    id: UUID = Field(
        description="Step ID; its result is served by `GET /steps/{id}/result`."
    )
    ordinal: int = Field(
        description="Position of the step within its message, starting at 1."
    )
    kind: str = Field(
        description="resolve_entity | sparql_query | previous_results | papers | clarification."
    )
    args: dict[str, Any] = Field(
        description="Arguments of the tool call, e.g. the query."
    )
    thinking: str | None = Field(
        description="The model's reasoning before this tool call, if any."
    )
    ok: bool | None = Field(
        description="Whether the step succeeded; null if it never finished."
    )
    count: int | None = Field(
        description="Number of rows (queries) or candidates (entity lookup)."
    )
    error: str | None = Field(
        description="Error text of a failed step."
    )
    duration_ms: int | None = Field(
        description="How long the step took; null if it never finished."
    )


class MessageOut(BaseModel):
    id: UUID = Field(
        description="Message ID."
    )
    turn: int = Field(
        description="Turn number; a user message and its answer share one."
    )
    role: Literal["user", "assistant"] = Field(
        description="Who produced the message."
    )
    content: str = Field(
        description="The user message or the LLM answer."
    )
    thinking: str | None = Field(
        description="Assistant only: the reasoning before the final answer, if any."
    )
    status: MessageStatus = Field(
        description="User messages are always `complete`. A `running` message whose turn "
        "can no longer be in progress is reported as `aborted`."
    )
    created_at: datetime = Field(
        description="Server timestamp."
    )
    steps: list[StepOut] = Field(
        description="Assistant only: the tool calls of the turn in order, without their results."
    )


class SessionDetail(BaseModel):
    id: UUID = Field(
        description="Session ID."
    )
    title: str | None = Field(
        description="Session title; null as long as the session has none."
    )
    updated_at: datetime = Field(
        description="When the last turn of the session completed (creation time before that)."
    )
    messages: list[MessageOut] = Field(
        description="Full chronological message history of the session."
    )


class SessionRename(BaseModel):
    title: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ] = Field(
        description="The new title. Surrounding whitespace is removed."
    )


class StepResult(BaseModel):
    step_id: UUID = Field(
        description="Step ID."
    )
    kind: str = Field(
        description="Kind of the step; decides the shape of `result`."
    )
    result: Any = Field(
        description="The stored result: SPARQL JSON for a query, the candidate list for an "
        "entity lookup, null for a step without a result."
    )


class ServiceHealth(BaseModel):
    status: Status = Field(
        description='Health status: "ok" (fully operational), "degraded" (partially available), "down" (unavailable).'
    )
    error: Optional[str] = Field(
        default=None,
        description="Error details if status is not 'ok'."
    )
    additional_attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Service-specific metadata, e.g. checked models or endpoint URL."
    )

class HealthResponse(BaseModel):
    status: str = Field(
        description='Overall health: "ok" (all services healthy), "degraded" (at least one degraded), "down" (at least one down).'
    )
    error: Optional[str] = Field(
        default=None,
        description="Semicolon-separated list of service errors. Null if all services are ok."
    )
    services: dict[str, ServiceHealth] = Field(
        description="Map of service name to its health status. "
        "Contains 'sparql_service' (GraphDB connectivity) and 'llm_service' (LLM API availability)."
    )

class ModelResponse(BaseModel):
    models: set[str] = Field(
        description="Set of model IDs available on the configured LLM API."
    )

class FullTable(BaseModel):
    columns: list[str] = Field(
        description="Ordered column names, as configured in the full_table_columns setting."
    )
    rows: list[dict[str, Any]] = Field(
        description="One object per row, keyed by column name. Numeric cells are coerced "
        "to int/float based on their SPARQL datatype; missing cells are null."
    )

class FullTableResponse(BaseModel):
    full_table: FullTable = Field(
        description="Predefined tabular view of the knowledge graph (columns + rows)."
    )

class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: str
    detail: str | None = None