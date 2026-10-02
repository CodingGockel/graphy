import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.dependencies import get_chat_service, get_db_sessionmaker
from src.main import app
from src.models.events import (
    AnswerEvent,
    DoneEvent,
    SessionEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from src.models.schemas import FullTable, FullTableResponse, ModelResponse
from src.util.exceptions import LLMServiceException, SessionNotFoundException


def _override_chat_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    return service


def _override_chat_run(events, *, error: Exception | None = None) -> dict:
    """Replace the chat service by one whose `run()` yields the given events (and then
    raises `error`), and the DB by a fake sessionmaker. Returns the captured call."""
    captured: dict = {}

    async def run(session_id, message, repo, state):
        captured.update(session_id=session_id, message=message, repo=repo, state=state)
        for event in events:
            yield event
        if error is not None:
            raise error

    service = MagicMock()
    service.run = run
    app.dependency_overrides[get_chat_service] = lambda: service

    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    app.dependency_overrides[get_db_sessionmaker] = lambda: (lambda: db)
    captured["db"] = db
    return captured


@pytest.fixture
def repo(mocker):
    """The repository the adapter builds around its DB session."""
    repo = MagicMock()
    repo.get_step_result = AsyncMock(return_value=None)
    mocker.patch("src.api.v1.chat.ChatRepository", return_value=repo)
    return repo


class TestChatEndpoint:
    """`POST /chat` is still JSON: the route consumes the event stream of the turn and
    assembles the old response from it."""

    def test_answer_and_session_come_from_the_events(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        captured = _override_chat_run([
            SessionEvent(session_id=sid, message_id=mid, title=None),
            AnswerEvent(delta="hello "),
            AnswerEvent(delta="back"),
            DoneEvent(message_id=mid),
        ])

        resp = client.post("/api/v1/chat/", json={"message": "hello"})

        assert resp.status_code == 200
        assert resp.json() == {
            "answer": "hello back",
            "session_id": str(sid),
            "llm_generated_query": "",
            "sparql_query_result": None,
        }
        assert captured["message"] == "hello"
        assert captured["session_id"] is None
        assert captured["repo"] is repo
        repo.get_step_result.assert_not_awaited()
        # the DB session is opened and closed by the route
        captured["db"].__aexit__.assert_awaited_once()

    def test_session_id_is_passed_on(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        captured = _override_chat_run([
            SessionEvent(session_id=sid, message_id=mid, title=None),
            AnswerEvent(delta="ok"),
            DoneEvent(message_id=mid),
        ])

        client.post("/api/v1/chat/", json={"message": "hello", "session_id": str(sid)})

        assert captured["session_id"] == sid

    def test_query_and_result_come_from_the_last_successful_query_step(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        first, failed, entity = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        _override_chat_run([
            SessionEvent(session_id=sid, message_id=mid, title=None),
            StepStartedEvent(step_id=first, ordinal=1, kind="sparql_query", args={"query": "Q1"}),
            StepFinishedEvent(step_id=first, ok=True, count=1, duration_ms=5),
            StepStartedEvent(step_id=failed, ordinal=2, kind="sparql_query", args={"query": "Q2"}),
            StepFinishedEvent(step_id=failed, ok=False, error="bad", duration_ms=5),
            StepStartedEvent(step_id=entity, ordinal=3, kind="resolve_entity", args={"term": "x"}),
            StepFinishedEvent(step_id=entity, ok=True, count=2, duration_ms=5),
            AnswerEvent(delta="answer"),
            DoneEvent(message_id=mid, row_count=1),
        ])
        repo.get_step_result.return_value = ("sparql_query", {"results": {"bindings": []}})

        resp = client.post("/api/v1/chat/", json={"message": "hello"})

        body = resp.json()
        assert body["llm_generated_query"] == "Q1"
        assert body["sparql_query_result"] == '{"results": {"bindings": []}}'
        repo.get_step_result.assert_awaited_once_with(first)

    def test_unknown_session_is_404(self, client, repo):
        _override_chat_run([], error=SessionNotFoundException("Session x not found"))

        resp = client.post(
            "/api/v1/chat/", json={"message": "hello", "session_id": str(uuid.uuid4())}
        )

        assert resp.status_code == 404
        assert resp.json()["status"] == "error"

    def test_domain_exception_keeps_its_status_code(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        _override_chat_run(
            [SessionEvent(session_id=sid, message_id=mid, title=None)],
            error=LLMServiceException("llm down"),
        )

        resp = client.post("/api/v1/chat/", json={"message": "hello"})

        assert resp.status_code == 503

    def test_post_chat_missing_message_is_422(self, client):
        _override_chat_run([])
        resp = client.post("/api/v1/chat/", json={})
        assert resp.status_code == 422


class TestModelsEndpoint:
    def test_get_models(self, client):
        service = _override_chat_service()
        service.models = AsyncMock(return_value=ModelResponse(models={"a", "b"}))

        resp = client.get("/api/v1/chat/models")

        assert resp.status_code == 200
        assert sorted(resp.json()["models"]) == ["a", "b"]


class TestFullTableEndpoint:
    def test_get_full_table(self, client):
        service = _override_chat_service()
        service.get_full_table = AsyncMock(
            return_value=FullTableResponse(
                full_table=FullTable(columns=["name"], rows=[{"name": "Rose"}])
            )
        )

        resp = client.get("/api/v1/chat/full_table?limit=5")

        assert resp.status_code == 200
        assert resp.json()["full_table"]["rows"] == [{"name": "Rose"}]
        service.get_full_table.assert_awaited_once_with(5)

    def test_invalid_limit_is_422(self, client):
        _override_chat_service()
        resp = client.get("/api/v1/chat/full_table?limit=0")  # ge=1
        assert resp.status_code == 422
