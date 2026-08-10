import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message
from src.db.repository import ChatRepository
from src.models.schemas import HistoryMessage, HistoryResponse, HistoryUpload


class SessionService:
    def __init__(self, db: AsyncSession):
        self.repo = ChatRepository(db)

    async def get_history(self, session_id: uuid.UUID) -> HistoryResponse:
        if not await self.repo.session_exists(session_id):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        messages = await self.repo.get_full_history(session_id)
        return HistoryResponse(
            session_id=session_id,
            messages=[self._to_schema(m) for m in messages],
        )

    async def replace_history(
        self, session_id: uuid.UUID, upload: HistoryUpload
    ) -> HistoryResponse:
        await self.repo.replace_history(session_id, upload.messages)
        messages = await self.repo.get_full_history(session_id)
        return HistoryResponse(
            session_id=session_id,
            messages=[self._to_schema(m) for m in messages],
        )

    async def delete_session(self, session_id: uuid.UUID) -> None:
        if not await self.repo.delete_session(session_id):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    @staticmethod
    def _to_schema(m: Message) -> HistoryMessage:
        return HistoryMessage(
            role=m.role,  # type: ignore[arg-type]
            content=m.content,
            sparql_query=m.sparql_query,
            sparql_results=m.sparql_results,
            created_at=m.created_at,
        )
