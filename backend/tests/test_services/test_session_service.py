import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.services.session_service import SessionService
from src.util.exceptions import SessionNotFoundException
from tests.factories import make_db_message, make_db_step


@pytest.fixture
def session_service(mocker):
    repo = AsyncMock()
    mocker.patch("src.services.session_service.ChatRepository", return_value=repo)
    service = SessionService(db=MagicMock())
    return service, repo


class TestGetHistory:
    async def test_returns_mapped_history(self, session_service):
        service, repo = session_service
        repo.session_exists = AsyncMock(return_value=True)
        step_id = uuid.uuid4()
        repo.get_full_history = AsyncMock(
            return_value=[
                make_db_message("user", "hi", created_at=datetime(2026, 1, 1)),
                make_db_message(
                    "assistant",
                    "answer",
                    steps=[
                        make_db_step(args={"query": "SELECT bad"}, ok=False, ordinal=1),
                        make_db_step(args={"query": "SELECT"}, ordinal=2, step_id=step_id),
                    ],
                ),
            ]
        )
        repo.get_step_result = AsyncMock(
            return_value=("sparql_query", {"results": {"bindings": []}})
        )
        sid = uuid.uuid4()
        result = await service.get_history(sid)
        assert result.session_id == sid
        assert [m.role for m in result.messages] == ["user", "assistant"]
        # filled from the turn's last successful query step
        assert result.messages[1].sparql_query == "SELECT"
        assert result.messages[1].sparql_results == '{"results": {"bindings": []}}'
        repo.get_step_result.assert_awaited_once_with(step_id)

    async def test_turn_that_reused_data_shows_the_reused_query_and_result(
        self, session_service
    ):
        service, repo = session_service
        repo.session_exists = AsyncMock(return_value=True)
        source = uuid.uuid4()
        repo.get_full_history = AsyncMock(
            return_value=[
                make_db_message("user", "and again"),
                make_db_message(
                    "assistant",
                    "answer",
                    steps=[
                        make_db_step(
                            kind="previous_results",
                            args={
                                "reference_turn": 1,
                                "source_step_id": str(source),
                                "query": "SELECT",
                            },
                        )
                    ],
                ),
            ]
        )
        repo.get_step_result = AsyncMock(
            return_value=("sparql_query", {"results": {"bindings": []}})
        )
        result = await service.get_history(uuid.uuid4())
        assert result.messages[1].sparql_query == "SELECT"
        assert result.messages[1].sparql_results == '{"results": {"bindings": []}}'
        repo.get_step_result.assert_awaited_once_with(source)

    async def test_message_without_query_step_has_no_sparql_fields(self, session_service):
        service, repo = session_service
        repo.session_exists = AsyncMock(return_value=True)
        repo.get_full_history = AsyncMock(
            return_value=[
                make_db_message("user", "hi"),
                make_db_message("assistant", "Which species?"),
            ]
        )
        result = await service.get_history(uuid.uuid4())
        assert result.messages[1].sparql_query is None
        assert result.messages[1].sparql_results is None
        repo.get_step_result.assert_not_awaited()

    async def test_assistant_messages_that_are_not_complete_are_left_out(self, session_service):
        service, repo = session_service
        repo.session_exists = AsyncMock(return_value=True)
        repo.get_full_history = AsyncMock(
            return_value=[
                make_db_message("user", "q1", turn=1),
                make_db_message("assistant", "", turn=1, status="error"),
                make_db_message("user", "q2", turn=2),
                make_db_message("assistant", "", turn=2, status="running"),
                make_db_message("user", "q3", turn=3),
                make_db_message("assistant", "a3", turn=3),
            ]
        )
        result = await service.get_history(uuid.uuid4())
        assert [m.content for m in result.messages] == ["q1", "q2", "q3", "a3"]

    async def test_missing_session_raises_404(self, session_service):
        service, repo = session_service
        repo.session_exists = AsyncMock(return_value=False)
        with pytest.raises(SessionNotFoundException):
            await service.get_history(uuid.uuid4())


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
