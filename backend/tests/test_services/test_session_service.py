import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.services.session_service import RUNNING_STALE_AFTER, SessionService
from src.util.exceptions import SessionNotFoundException, StepNotFoundException
from tests.factories import make_db_message, make_db_session, make_db_step


@pytest.fixture
def session_service(mocker):
    repo = AsyncMock()
    mocker.patch("src.services.session_service.ChatRepository", return_value=repo)
    service = SessionService(db=MagicMock())
    return service, repo


class TestGetSessions:
    async def test_returns_metadata_with_message_counts(self, session_service):
        service, repo = session_service
        first = make_db_session(title="First")
        empty = make_db_session()
        repo.get_sessions = AsyncMock(return_value=[first, empty])
        repo.count_messages = AsyncMock(return_value={first.id: 4})

        result = await service.get_sessions([first.id, empty.id])

        assert [(s.id, s.title, s.message_count) for s in result] == [
            (first.id, "First", 4),
            # a session without messages is missing from the counts
            (empty.id, None, 0),
        ]
        assert result[0].updated_at == first.updated_at

    async def test_unknown_ids_are_omitted(self, session_service):
        service, repo = session_service
        known = make_db_session()
        repo.get_sessions = AsyncMock(return_value=[known])
        repo.count_messages = AsyncMock(return_value={})

        result = await service.get_sessions([known.id, uuid.uuid4()])

        assert [s.id for s in result] == [known.id]
        repo.count_messages.assert_awaited_once_with([known.id])


class TestGetSession:
    async def test_returns_messages_with_their_steps(self, session_service):
        service, repo = session_service
        session = make_db_session(title="Title")
        repo.get_sessions = AsyncMock(return_value=[session])
        failed = make_db_step(
            args={"query": "SELECT bad"}, ok=False, ordinal=1, error="bad", duration_ms=3
        )
        ok = make_db_step(
            args={"query": "SELECT"}, ordinal=2, count=7, thinking="hm", duration_ms=40
        )
        question = make_db_message("user", "hi")
        answer = make_db_message("assistant", "answer", steps=[failed, ok])
        answer.thinking = "so"
        repo.get_full_history = AsyncMock(return_value=[question, answer])

        result = await service.get_session(session.id)

        assert (result.id, result.title, result.updated_at) == (
            session.id, "Title", session.updated_at,
        )
        assert [(m.id, m.turn, m.role, m.content, m.status) for m in result.messages] == [
            (question.id, 1, "user", "hi", "complete"),
            (answer.id, 1, "assistant", "answer", "complete"),
        ]
        assert result.messages[0].steps == []
        assert result.messages[1].thinking == "so"
        steps = result.messages[1].steps
        assert [(s.id, s.ordinal, s.ok, s.count, s.error) for s in steps] == [
            (failed.id, 1, False, None, "bad"),
            (ok.id, 2, True, 7, None),
        ]
        assert steps[1].args == {"query": "SELECT"}
        assert steps[1].thinking == "hm"
        assert steps[1].duration_ms == 40

    async def test_step_results_are_not_loaded(self, session_service):
        service, repo = session_service
        repo.get_sessions = AsyncMock(return_value=[make_db_session()])
        repo.get_full_history = AsyncMock(
            return_value=[make_db_message("assistant", "answer", steps=[make_db_step()])]
        )

        result = await service.get_session(uuid.uuid4())

        repo.get_step_result.assert_not_awaited()
        assert "result" not in result.messages[0].steps[0].model_dump()

    async def test_all_turns_are_returned_with_their_status(self, session_service):
        service, repo = session_service
        repo.get_sessions = AsyncMock(return_value=[make_db_session()])
        repo.get_full_history = AsyncMock(
            return_value=[
                make_db_message("user", "q1", turn=1),
                make_db_message("assistant", "", turn=1, status="error"),
                make_db_message("user", "q2", turn=2),
                make_db_message("assistant", "part", turn=2, status="aborted"),
            ]
        )

        result = await service.get_session(uuid.uuid4())

        assert [(m.turn, m.role, m.status) for m in result.messages] == [
            (1, "user", "complete"),
            (1, "assistant", "error"),
            (2, "user", "complete"),
            (2, "assistant", "aborted"),
        ]

    async def test_stale_running_message_is_reported_as_aborted(self, session_service):
        service, repo = session_service
        repo.get_sessions = AsyncMock(return_value=[make_db_session()])
        stale = datetime.now(timezone.utc) - RUNNING_STALE_AFTER - timedelta(seconds=1)
        repo.get_full_history = AsyncMock(
            return_value=[make_db_message("assistant", "", status="running", created_at=stale)]
        )

        result = await service.get_session(uuid.uuid4())

        assert result.messages[0].status == "aborted"

    async def test_young_running_message_stays_running(self, session_service):
        service, repo = session_service
        repo.get_sessions = AsyncMock(return_value=[make_db_session()])
        young = datetime.now(timezone.utc) - RUNNING_STALE_AFTER + timedelta(minutes=1)
        repo.get_full_history = AsyncMock(
            return_value=[make_db_message("assistant", "", status="running", created_at=young)]
        )

        result = await service.get_session(uuid.uuid4())

        assert result.messages[0].status == "running"

    async def test_missing_session_raises_404(self, session_service):
        service, repo = session_service
        repo.get_sessions = AsyncMock(return_value=[])
        with pytest.raises(SessionNotFoundException):
            await service.get_session(uuid.uuid4())
        repo.get_full_history.assert_not_awaited()


class TestRenameSession:
    async def test_sets_the_title_as_manual(self, session_service):
        service, repo = session_service
        session = make_db_session(title="New")
        repo.set_title = AsyncMock(return_value=True)
        repo.get_sessions = AsyncMock(return_value=[session])
        repo.count_messages = AsyncMock(return_value={session.id: 2})

        result = await service.rename_session(session.id, "New")

        repo.set_title.assert_awaited_once_with(session.id, "New", manual=True)
        assert (result.id, result.title, result.message_count) == (session.id, "New", 2)

    async def test_missing_session_raises_404(self, session_service):
        service, repo = session_service
        repo.set_title = AsyncMock(return_value=False)
        with pytest.raises(SessionNotFoundException):
            await service.rename_session(uuid.uuid4(), "New")


class TestDeleteSession:
    async def test_success(self, session_service):
        service, repo = session_service
        repo.delete_session = AsyncMock(return_value=True)
        assert await service.delete_session(uuid.uuid4()) is None

    async def test_missing_session_raises_404(self, session_service):
        service, repo = session_service
        repo.delete_session = AsyncMock(return_value=False)
        with pytest.raises(SessionNotFoundException):
            await service.delete_session(uuid.uuid4())


class TestGetStepResult:
    async def test_returns_kind_and_result(self, session_service):
        service, repo = session_service
        step_id = uuid.uuid4()
        repo.get_step_result = AsyncMock(
            return_value=("sparql_query", {"results": {"bindings": []}})
        )

        result = await service.get_step_result(step_id)

        assert (result.step_id, result.kind) == (step_id, "sparql_query")
        assert result.result == {"results": {"bindings": []}}

    async def test_step_without_a_result_is_not_a_404(self, session_service):
        service, repo = session_service
        repo.get_step_result = AsyncMock(return_value=("clarification", None))

        result = await service.get_step_result(uuid.uuid4())

        assert result.result is None

    async def test_unknown_step_raises_404(self, session_service):
        service, repo = session_service
        repo.get_step_result = AsyncMock(return_value=None)
        with pytest.raises(StepNotFoundException):
            await service.get_step_result(uuid.uuid4())
