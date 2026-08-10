"""Small builders for mocking the OpenAI client surface and DB rows in unit tests."""
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


def make_models(*ids: str) -> SimpleNamespace:
    """Mimic the object returned by `client.models.list` (has `.data`)."""
    return SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])


def make_db_message(
    role: str,
    content: str,
    sparql_query=None,
    sparql_results=None,
    created_at=None,
) -> MagicMock:
    """Mimic a `src.db.models.Message` ORM row."""
    m = MagicMock()
    m.role = role
    m.content = content
    m.sparql_query = sparql_query
    m.sparql_results = sparql_results
    m.created_at = created_at
    return m
