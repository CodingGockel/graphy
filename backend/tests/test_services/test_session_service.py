import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.models.schemas import HistoryMessage, HistoryUpload
from src.services.session_service import SessionService
from tests.factories import make_db_message


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
        repo.get_full_history = AsyncMock(
            return_value=[
                make_db_message("user", "hi", created_at=datetime(2026, 1, 1)),
                make_db_message(
                    "assistant", "answer", sparql_query="SELECT", sparql_results="{}"
                ),
            ]
        )
        sid = uuid.uuid4()
        result = await service.get_history(sid)
        assert result.session_id == sid
        assert [m.role for m in result.messages] == ["user", "assistant"]
        assert result.messages[1].sparql_query == "SELECT"

    async def test_missing_session_raises_404(self, session_service):
        service, repo = session_service
        repo.session_exists = AsyncMock(return_value=False)
        with pytest.raises(HTTPException) as exc:
            await service.get_history(uuid.uuid4())
        assert exc.value.status_code == 404


class TestReplaceHistory:
    async def test_delegates_and_returns_updated(self, session_service):
        service, repo = session_service
        repo.replace_history = AsyncMock()
        repo.get_full_history = AsyncMock(
            return_value=[make_db_message("user", "new message")]
        )
        sid = uuid.uuid4()
        upload = HistoryUpload(messages=[HistoryMessage(role="user", content="new message")])

        result = await service.replace_history(sid, upload)

        repo.replace_history.assert_awaited_once_with(sid, upload.messages)
        assert result.messages[0].content == "new message"


class TestDeleteSession:
    async def test_success(self, session_service):
        service, repo = session_service
        repo.delete_session = AsyncMock(return_value=True)
        assert await service.delete_session(uuid.uuid4()) is None

    async def test_missing_session_raises_404(self, session_service):
        service, repo = session_service
        repo.delete_session = AsyncMock(return_value=False)
        with pytest.raises(HTTPException) as exc:
            await service.delete_session(uuid.uuid4())
        assert exc.value.status_code == 404
