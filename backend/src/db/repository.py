import uuid
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import ChatSession, Message, Step


def reusable_data(message: Message) -> tuple[uuid.UUID, str] | None:
    """The data a later turn can reuse from an assistant message, as `(step id, query)`
    of the step that holds the result: the message's last successful `sparql_query`
    step, or the step a successful `previous_results` step pointed at (so reused data
    stays reusable in the following turns). Expects `message.steps` to be loaded."""
    for step in reversed(message.steps):
        if not step.ok:
            continue
        if step.kind == "sparql_query":
            return step.id, step.args.get("query", "")
        if step.kind == "previous_results":
            try:
                return uuid.UUID(step.args["source_step_id"]), step.args.get("query", "")
            except (KeyError, TypeError, ValueError):
                continue
    return None


def _in_turn_order(messages: list[Message]) -> list[Message]:
    """Chronological order: by turn, the user message before the assistant message."""
    return sorted(messages, key=lambda m: (m.turn, m.role != "user"))


class ChatRepository:
    """Every method ends its transaction, reads included: a DB session can live as
    long as a chat stream, and a read that leaves its transaction open would pin a
    pooled connection ("idle in transaction") through every LLM call."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def rollback(self) -> None:
        """Leave a transaction that a failed statement has aborted, so the session
        can be used again."""
        await self._session.rollback()

    # --- sessions ---------------------------------------------------------

    async def create_session(self) -> uuid.UUID:
        chat_session = ChatSession(id=uuid.uuid4())
        self._session.add(chat_session)
        await self._session.commit()
        return chat_session.id

    async def session_exists(self, session_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(ChatSession.id).where(ChatSession.id == session_id)
        )
        exists = result.scalar_one_or_none() is not None
        await self._session.commit()
        return exists

    async def get_sessions(self, session_ids: list[uuid.UUID]) -> list[ChatSession]:
        """The sessions with the given ids, most recently updated first. Unknown ids
        are simply missing from the result."""
        if not session_ids:
            return []
        result = await self._session.execute(
            select(ChatSession)
            .where(ChatSession.id.in_(session_ids))
            .order_by(ChatSession.updated_at.desc())
        )
        sessions = list(result.scalars().all())
        await self._session.commit()
        return sessions

    async def set_title(self, session_id: uuid.UUID, title: str, manual: bool) -> bool:
        """Set the session title. Returns whether a session with that id existed."""
        result = await self._session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(title=title, title_is_manual=manual)
        )
        await self._session.commit()
        return result.rowcount > 0  # type: ignore

    async def touch_session(self, session_id: uuid.UUID) -> None:
        """Bump `updated_at` (the sidebar sorts by it)."""
        await self._session.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(updated_at=func.now())
        )
        await self._session.commit()

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        """Delete the session row (cascade removes its messages and their steps).
        Returns whether a session with that id existed."""
        result = await self._session.execute(
            delete(ChatSession).where(ChatSession.id == session_id)
        )
        await self._session.commit()
        return result.rowcount > 0  # type: ignore

    # --- messages ---------------------------------------------------------

    async def next_turn(self, session_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(Message.turn), 0)).where(
                Message.session_id == session_id
            )
        )
        turn = result.scalar_one() + 1
        await self._session.commit()
        return turn

    async def add_message(
        self,
        session_id: uuid.UUID,
        turn: int,
        role: str,
        content: str,
        status: str,
    ) -> uuid.UUID:
        message = Message(
            id=uuid.uuid4(),
            session_id=session_id,
            turn=turn,
            role=role,
            content=content,
            status=status,
        )
        self._session.add(message)
        await self._session.commit()
        return message.id

    async def finish_message(
        self,
        message_id: uuid.UUID,
        content: str,
        thinking: str | None,
        status: str,
    ) -> None:
        await self._session.execute(
            update(Message)
            .where(Message.id == message_id)
            .values(content=content, thinking=thinking, status=status)
        )
        await self._session.commit()

    # --- steps ------------------------------------------------------------

    async def start_step(
        self,
        message_id: uuid.UUID,
        ordinal: int,
        kind: str,
        args: dict[str, Any],
        thinking: str | None = None,
    ) -> uuid.UUID:
        step = Step(
            id=uuid.uuid4(),
            message_id=message_id,
            ordinal=ordinal,
            kind=kind,
            args=args,
            thinking=thinking,
        )
        self._session.add(step)
        await self._session.commit()
        return step.id

    async def finish_step(
        self,
        step_id: uuid.UUID,
        ok: bool,
        count: int | None,
        result: Any | None,
        error: str | None,
        duration_ms: int,
    ) -> None:
        await self._session.execute(
            update(Step)
            .where(Step.id == step_id)
            .values(ok=ok, count=count, result=result, error=error, duration_ms=duration_ms)
        )
        await self._session.commit()

    async def get_step_result(self, step_id: uuid.UUID) -> tuple[str, Any] | None:
        """`(kind, result)` of a step, or None if there is no such step. The only
        place a step result is read."""
        result = await self._session.execute(
            select(Step.kind, Step.result).where(Step.id == step_id)
        )
        row = result.one_or_none()
        await self._session.commit()
        return (row[0], row[1]) if row is not None else None

    # --- reads ------------------------------------------------------------

    async def get_history(self, session_id: uuid.UUID, turns: int) -> list[Message]:
        """The messages of the last `turns` complete turns (assistant message with
        status `complete`) in chronological order, with their steps but without the
        step results."""
        complete_turns = (
            select(Message.turn)
            .where(
                Message.session_id == session_id,
                Message.role == "assistant",
                Message.status == "complete",
            )
            .order_by(Message.turn.desc())
            .limit(turns)
        )
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id, Message.turn.in_(complete_turns))
            .options(selectinload(Message.steps))
        )
        messages = list(result.scalars().all())
        await self._session.commit()
        return _in_turn_order(messages)

    async def get_full_history(self, session_id: uuid.UUID) -> list[Message]:
        """All messages of a session in chronological order, with their steps but
        without the step results."""
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .options(selectinload(Message.steps))
        )
        messages = list(result.scalars().all())
        await self._session.commit()
        return _in_turn_order(messages)
