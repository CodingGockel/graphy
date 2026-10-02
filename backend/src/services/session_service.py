import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message
from src.db.repository import ChatRepository, reusable_data
from src.models.schemas import HistoryMessage, HistoryResponse
from src.util.exceptions import SessionNotFoundException
from src.util.sparql_utils import results_to_text


class SessionService:
    def __init__(self, db: AsyncSession):
        self.repo = ChatRepository(db)

    async def get_history(self, session_id: uuid.UUID) -> HistoryResponse:
        if not await self.repo.session_exists(session_id):
            raise SessionNotFoundException(f"Session {session_id} not found")
        messages = await self.repo.get_full_history(session_id)
        # An assistant message that is not complete (failed, aborted, running) has no
        # place in this response shape; its question is kept, as before the rework.
        visible = [m for m in messages if m.role == "user" or m.status == "complete"]
        return HistoryResponse(
            session_id=session_id,
            messages=[await self._to_schema(m) for m in visible],
        )

    async def delete_session(self, session_id: uuid.UUID) -> None:
        if not await self.repo.delete_session(session_id):
            raise SessionNotFoundException(f"Session {session_id} not found")

    async def _to_schema(self, m: Message) -> HistoryMessage:
        """Query and results are the turn's reusable data (see reusable_data)."""
        sparql_query: str | None = None
        sparql_results: str | None = None
        data = reusable_data(m) if m.role == "assistant" else None
        if data is not None:
            step_id, sparql_query = data
            stored = await self.repo.get_step_result(step_id)
            if stored is not None and stored[1] is not None:
                sparql_results = results_to_text(stored[1])
        return HistoryMessage(
            role=m.role,  # type: ignore[arg-type]
            content=m.content,
            sparql_query=sparql_query,
            sparql_results=sparql_results,
            created_at=m.created_at,
        )
