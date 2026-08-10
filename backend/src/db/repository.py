import uuid

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChatSession, Message
from src.models.schemas import HistoryMessage


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_session(self) -> uuid.UUID:
        chat_session = ChatSession(id=uuid.uuid4())
        self._session.add(chat_session)
        await self._session.commit()
        return chat_session.id

    async def session_exists(self, session_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ChatSession.id).where(ChatSession.id == session_id)
        )
        return result.scalar_one_or_none() is not None

    async def save_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        sparql_query: str | None = None,
        sparql_results: str | None = None,
    ) -> None:
        msg = Message(
            session_id=session_id,
            role=role,
            content=content,
            sparql_query=sparql_query,
            sparql_results=sparql_results,
        )
        self._session.add(msg)
        await self._session.commit()

    async def get_history(
        self, session_id: uuid.UUID, limit: int = 10
    ) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.id.desc())
            .limit(limit * 2)
        )
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def get_full_history(self, session_id: uuid.UUID) -> list[Message]:
        """All messages of a session in stable chronological (insertion) order."""
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.id.asc())
        )
        return list(result.scalars().all())

    async def ensure_session(self, session_id: uuid.UUID) -> None:
        """Create a session row with the given id if it doesn't exist yet."""
        if not await self.session_exists(session_id):
            self._session.add(ChatSession(id=session_id))
            await self._session.commit()

    async def replace_history(
        self, session_id: uuid.UUID, messages: list[HistoryMessage]
    ) -> None:
        """Replace all messages of a session with the given list, creating the
        session if it does not exist. Insertion order defines chronology."""
        await self.ensure_session(session_id)
        await self._session.execute(
            delete(Message).where(Message.session_id == session_id)
        )
        for m in messages:
            self._session.add(
                Message(
                    session_id=session_id,
                    role=m.role,
                    content=m.content,
                    sparql_query=m.sparql_query,
                    sparql_results=m.sparql_results,
                )
            )
        await self._session.commit()

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        """Delete the session row (cascade removes its messages). Returns whether
        a session with that id existed."""
        result = await self._session.execute(
            delete(ChatSession).where(ChatSession.id == session_id)
        )
        await self._session.commit()
        return result.rowcount > 0 #type: ignore
