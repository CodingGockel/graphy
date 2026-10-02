"""Small builders for mocking the OpenAI client surface and DB rows in unit tests."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock


def make_tool_call(name: str, arguments_json: str, call_id: str = "call_1") -> MagicMock:
    """Mimic one entry of `response.choices[0].message.tool_calls`."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = arguments_json
    return tc


def make_message(content=None, tool_calls=None) -> MagicMock:
    """Mimic `response.choices[0].message`."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    return msg


def make_completion(message, finish_reason: str = "stop") -> SimpleNamespace:
    """Mimic the object returned by `client.chat.completions.create`."""
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


class FakeStream:
    """Mimic the stream returned by `client.chat.completions.create(stream=True)`."""

    def __init__(self, chunks, error: Exception | None = None):
        self._chunks = list(chunks)
        self._error = error
        self.closed = False

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk
        if self._error is not None:
            raise self._error

    async def close(self) -> None:
        self.closed = True


def make_chunk(
    content=None, tool_calls=None, finish_reason=None, reasoning_content=None
) -> SimpleNamespace:
    """Mimic one chunk of a streamed completion."""
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    if reasoning_content is not None:
        delta.reasoning_content = reasoning_content
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


def make_tool_call_delta(index: int, call_id=None, name=None, arguments=None) -> SimpleNamespace:
    """Mimic one entry of `chunk.choices[0].delta.tool_calls`."""
    return SimpleNamespace(
        index=index, id=call_id, function=SimpleNamespace(name=name, arguments=arguments)
    )


def make_models(*ids: str) -> SimpleNamespace:
    """Mimic the object returned by `client.models.list` (has `.data`)."""
    return SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])


def make_db_step(
    kind: str = "sparql_query",
    args=None,
    ok=True,
    count=None,
    ordinal: int = 1,
    error=None,
    thinking=None,
    duration_ms=None,
    step_id=None,
) -> MagicMock:
    """Mimic a `src.db.models.Step` ORM row (without its deferred `result`)."""
    s = MagicMock()
    s.id = step_id or uuid.uuid4()
    s.ordinal = ordinal
    s.kind = kind
    s.args = args if args is not None else {}
    s.thinking = thinking
    s.ok = ok
    s.count = count
    s.error = error
    s.duration_ms = duration_ms
    return s


def make_db_message(
    role: str,
    content: str,
    turn: int = 1,
    status: str = "complete",
    steps=None,
    created_at=None,
) -> MagicMock:
    """Mimic a `src.db.models.Message` ORM row."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.role = role
    m.content = content
    m.turn = turn
    m.status = status
    m.thinking = None
    m.steps = steps if steps is not None else []
    m.created_at = created_at or datetime.now(timezone.utc)
    return m


def make_db_session(session_id=None, title=None, updated_at=None) -> MagicMock:
    """Mimic a `src.db.models.ChatSession` ORM row."""
    s = MagicMock()
    s.id = session_id or uuid.uuid4()
    s.title = title
    s.updated_at = updated_at or datetime.now(timezone.utc)
    return s
