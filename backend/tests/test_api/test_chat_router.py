import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.dependencies import get_chat_service, get_db_sessionmaker
from src.api.v1 import chat as chat_route
from src.main import app
from src.models.events import (
    SSE_PING,
    AnswerEvent,
    DoneEvent,
    ErrorEvent,
    SessionEvent,
    StepFinishedEvent,
    StepStartedEvent,
    encode_sse,
)
from src.models.schemas import ChatRequest
from src.services.chat_service import TurnState
from src.util.exceptions import (
    LLMNoContentException,
    LLMServiceException,
    SessionNotFoundException,
    SparqlDatabaseException,
    SparqlDatabaseStatusCode,
)


def _override_chat_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_chat_service] = lambda: service
    return service


def _fake_sessionmaker() -> MagicMock:
    """A sessionmaker whose every call opens a new fake DB session; `.opened` lists them."""
    opened: list[MagicMock] = []

    def make():
        db = MagicMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        opened.append(db)
        return db

    sessionmaker = MagicMock(side_effect=make)
    sessionmaker.opened = opened
    return sessionmaker


def _service(events=(), *, error: Exception | None = None, delay: float = 0.0):
    """A chat service whose `run()` yields the given events (after `delay` seconds
    each) and then raises `error`. Returns the service and the captured call."""
    captured: dict = {}

    async def run(session_id, message, repo, state):
        captured.update(session_id=session_id, message=message, repo=repo, state=state)
        for event in events:
            if delay:
                await asyncio.sleep(delay)
            yield event
        if error is not None:
            raise error

    service = MagicMock()
    service.run = run
    return service, captured


def _override_chat_run(events=(), **kwargs) -> dict:
    """Wire a fake service and a fake sessionmaker into the app."""
    service, captured = _service(events, **kwargs)
    sessionmaker = _fake_sessionmaker()
    app.dependency_overrides[get_chat_service] = lambda: service
    app.dependency_overrides[get_db_sessionmaker] = lambda: sessionmaker
    captured["sessionmaker"] = sessionmaker
    return captured


@pytest.fixture
def repo(mocker):
    """The repository the route builds around each of its DB sessions."""
    repo = MagicMock()
    repo.session_exists = AsyncMock(return_value=True)
    repo.abort_message = AsyncMock()
    mocker.patch("src.api.v1.chat.ChatRepository", return_value=repo)
    return repo


def _turn(sid: uuid.UUID, mid: uuid.UUID) -> list:
    step = uuid.uuid4()
    return [
        SessionEvent(session_id=sid, message_id=mid, title=None),
        StepStartedEvent(step_id=step, ordinal=1, kind="sparql_query", args={"query": "Q"}),
        StepFinishedEvent(step_id=step, ok=True, count=1, duration_ms=5),
        AnswerEvent(delta="hällo\nback"),
        DoneEvent(message_id=mid, row_count=1),
    ]


class TestChatStream:
    """`POST /chat` answers with the events of the turn as Server-Sent Events."""

    def test_events_are_sent_as_sse_frames(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        events = _turn(sid, mid)
        captured = _override_chat_run(events)

        resp = client.post("/api/v1/chat", json={"message": "hello"})

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"
        assert resp.text == "".join(encode_sse(e) for e in events)
        assert captured["message"] == "hello"
        assert captured["session_id"] is None
        assert captured["repo"] is repo

    def test_db_session_lives_inside_the_stream(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        captured = _override_chat_run(_turn(sid, mid))

        client.post("/api/v1/chat", json={"message": "hello"})

        # No session id → no existence check: the only DB session is the stream's.
        [db] = captured["sessionmaker"].opened
        db.__aexit__.assert_awaited_once()
        repo.session_exists.assert_not_awaited()

    def test_known_session_is_checked_and_passed_on(self, client, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        captured = _override_chat_run(_turn(sid, mid))

        resp = client.post("/api/v1/chat", json={"message": "hello", "session_id": str(sid)})

        assert resp.status_code == 200
        repo.session_exists.assert_awaited_once_with(sid)
        assert captured["session_id"] == sid
        # one short-lived session for the check, one for the stream
        assert len(captured["sessionmaker"].opened) == 2

    def test_unknown_session_is_404_as_json(self, client, repo):
        captured = _override_chat_run([])
        repo.session_exists.return_value = False

        resp = client.post(
            "/api/v1/chat", json={"message": "hello", "session_id": str(uuid.uuid4())}
        )

        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json()["status"] == "error"
        assert "session_id" not in captured  # the turn never started

    @pytest.mark.parametrize(
        "error, kind",
        [
            (LLMServiceException("llm down"), "llm_unavailable"),
            (LLMNoContentException("empty"), "llm_no_content"),
            (SparqlDatabaseException("graphdb down"), "sparql_unavailable"),
            (SparqlDatabaseStatusCode("HTTP 500"), "sparql_failed"),
            (SessionNotFoundException("deleted meanwhile"), "session_not_found"),
        ],
    )
    def test_domain_exception_becomes_an_error_event(self, client, repo, error, kind):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        session = SessionEvent(session_id=sid, message_id=mid, title=None)
        _override_chat_run([session], error=error)

        resp = client.post("/api/v1/chat", json={"message": "hello"})

        # The stream had started: the status stays 200, the error is the last frame.
        assert resp.status_code == 200
        assert resp.text == encode_sse(session) + encode_sse(
            ErrorEvent(kind=kind, message=str(error))
        )

    def test_unexpected_exception_becomes_an_internal_error_event(self, client, repo):
        _override_chat_run([], error=RuntimeError("secret detail"))

        resp = client.post("/api/v1/chat", json={"message": "hello"})

        assert resp.status_code == 200
        assert resp.text == encode_sse(ErrorEvent(kind="internal", message="Internal server error"))
        assert "secret detail" not in resp.text

    def test_idle_stream_sends_pings(self, client, repo, mocker):
        mocker.patch.object(chat_route, "PING_INTERVAL", 0.01)
        sid, mid = uuid.uuid4(), uuid.uuid4()
        _override_chat_run(
            [SessionEvent(session_id=sid, message_id=mid, title=None), DoneEvent(message_id=mid)],
            delay=0.1,
        )

        resp = client.post("/api/v1/chat", json={"message": "hello"})

        assert resp.text.startswith(SSE_PING)
        assert resp.text.endswith(encode_sse(DoneEvent(message_id=mid)))

    def test_post_chat_missing_message_is_422(self, client):
        _override_chat_run([])
        resp = client.post("/api/v1/chat", json={})
        assert resp.status_code == 422


class TestAbort:
    """A client that disconnects: the response generator ends, the producer is
    cancelled and stores the turn as aborted."""

    @staticmethod
    def _hanging_service(started: asyncio.Event, mid: uuid.UUID):
        """A turn that announces itself, has a partial answer and then never ends."""

        async def run(session_id, message, repo, state):
            state.message_id = mid
            state.answer = "partial"
            yield SessionEvent(session_id=uuid.uuid4(), message_id=mid, title=None)
            started.set()
            await asyncio.Event().wait()

        service = MagicMock()
        service.run = run
        return service

    async def test_cancelled_producer_marks_the_message_aborted(self, repo):
        mid = uuid.uuid4()
        started = asyncio.Event()
        sessionmaker = _fake_sessionmaker()
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            chat_route._produce(
                self._hanging_service(started, mid),
                sessionmaker,
                ChatRequest(message="hi"),
                queue,
                TurnState(),
            )
        )
        await started.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # through a second DB session, with the partial answer from the turn state
        assert len(sessionmaker.opened) == 2
        repo.abort_message.assert_awaited_once_with(mid, content="partial", thinking=None)
        # no end marker and no error event: nobody is listening any more
        assert queue.qsize() == 1

    async def test_turn_that_never_got_a_message_has_nothing_to_abort(self, repo):
        sessionmaker = _fake_sessionmaker()
        await chat_route._mark_aborted(sessionmaker, TurnState())
        repo.abort_message.assert_not_awaited()
        assert sessionmaker.opened == []

    async def test_failing_to_store_the_abort_is_swallowed(self, repo):
        repo.abort_message.side_effect = ConnectionError("db gone")
        await chat_route._mark_aborted(_fake_sessionmaker(), TurnState(message_id=uuid.uuid4()))

    async def test_closing_the_response_cancels_the_producer(self, repo):
        mid = uuid.uuid4()
        started = asyncio.Event()
        stream = chat_route._stream(
            self._hanging_service(started, mid), _fake_sessionmaker(), ChatRequest(message="hi")
        )

        first = await anext(stream)
        assert first.startswith("event: session\n")
        await started.wait()
        [producer] = chat_route._producers

        await stream.aclose()  # what the server does when the client is gone
        with pytest.raises(asyncio.CancelledError):
            await producer

        repo.abort_message.assert_awaited_once_with(mid, content="partial", thinking=None)
        assert not chat_route._producers

    async def test_finished_turn_is_not_aborted(self, repo):
        sid, mid = uuid.uuid4(), uuid.uuid4()
        service, _ = _service(_turn(sid, mid))

        frames = [
            frame
            async for frame in chat_route._stream(
                service, _fake_sessionmaker(), ChatRequest(message="hi")
            )
        ]

        assert len(frames) == 5
        repo.abort_message.assert_not_awaited()
