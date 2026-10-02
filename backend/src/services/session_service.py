import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message
from src.db.repository import ChatRepository, last_query_step
from src.models.schemas import HistoryMessage, HistoryResponse
from src.util.sparql_utils import results_to_text


class SessionService:
    def __init__(self, db: AsyncSession):
        self.repo = ChatRepository(db)

    async def get_history(self, session_id: uuid.UUID) -> HistoryResponse:
        if not await self.repo.session_exists(session_id):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
        messages = await self.repo.get_full_history(session_id)
        return HistoryResponse(
            session_id=session_id,
            messages=[await self._to_schema(m) for m in messages],
        )

    async def delete_session(self, session_id: uuid.UUID) -> None:
        if not await self.repo.delete_session(session_id):
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    async def _to_schema(self, m: Message) -> HistoryMessage:
        """Query and results come from the turn's last successful query step."""
        sparql_query: str | None = None
        sparql_results: str | None = None
        step = last_query_step(m) if m.role == "assistant" else None
        if step is not None:
            sparql_query = step.args.get("query")
            stored = await self.repo.get_step_result(step.id)
            if stored is not None and stored[1] is not None:
                sparql_results = results_to_text(stored[1])
        return HistoryMessage(
            role=m.role,  # type: ignore[arg-type]
            content=m.content,
            sparql_query=sparql_query,
            sparql_results=sparql_results,
            created_at=m.created_at,
        )
