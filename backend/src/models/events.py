"""The event contract of a chat turn, sent as Server-Sent Events.

Order of a turn: `session` → (`step_started` → `step_finished`)* → `answer`+ → `done`.
`thinking` and `session_title` may appear anywhere after `session`; a `thinking` delta
belongs to whatever comes next (the following `step_started`, or the answer). `error`
ends the stream; no `done` follows it. Step results are never part of an event.
"""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

StepKind = Literal[
    "resolve_entity", "sparql_query", "previous_results", "clarification"
]
ErrorKind = Literal[
    "llm_unavailable",
    "llm_no_content",
    "sparql_unavailable",
    "sparql_failed",
    "session_not_found",
    "internal",
]


class SessionEvent(BaseModel):
    """First event of every turn. `message_id` is the assistant message."""
    event: Literal["session"] = "session"
    session_id: UUID
    message_id: UUID
    title: str | None


class SessionTitleEvent(BaseModel):
    event: Literal["session_title"] = "session_title"
    session_id: UUID
    title: str


class StepStartedEvent(BaseModel):
    event: Literal["step_started"] = "step_started"
    step_id: UUID
    ordinal: int
    kind: StepKind
    args: dict[str, Any]


class StepFinishedEvent(BaseModel):
    """`count` is the number of rows or candidates; `error` is set on a failed step."""
    event: Literal["step_finished"] = "step_finished"
    step_id: UUID
    ok: bool
    count: int | None = None
    error: str | None = None
    duration_ms: int


class ThinkingEvent(BaseModel):
    event: Literal["thinking"] = "thinking"
    delta: str


class AnswerEvent(BaseModel):
    event: Literal["answer"] = "answer"
    delta: str


class DoneEvent(BaseModel):
    """Only sent for a complete turn. `row_count` is that of the data the answer is based on."""
    event: Literal["done"] = "done"
    message_id: UUID
    row_count: int | None = None


class ErrorEvent(BaseModel):
    event: Literal["error"] = "error"
    kind: ErrorKind
    message: str


ChatEvent = (
    SessionEvent
    | SessionTitleEvent
    | StepStartedEvent
    | StepFinishedEvent
    | ThinkingEvent
    | AnswerEvent
    | DoneEvent
    | ErrorEvent
)

# SSE comment line, sent as a heartbeat so proxies keep an idle stream open.
SSE_PING = ": ping\n\n"


def encode_sse(event: ChatEvent) -> str:
    """One SSE frame: `event: <name>\\ndata: <json>\\n\\n`. The JSON is a single line
    (newlines inside strings are escaped) and does not repeat the event name."""
    data = event.model_dump_json(exclude={"event"})
    return f"event: {event.event}\ndata: {data}\n\n"
