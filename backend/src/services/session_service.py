import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChatSession, Message
from src.db.repository import ChatRepository
from src.models.schemas import (
    MessageOut,
    SessionDetail,
    SessionSummary,
    StepOut,
    StepResult,
)
from src.util.exceptions import SessionNotFoundException, StepNotFoundException

# A `running` message older than this is reported as `aborted`: its turn died with the
# server (nothing cleans such rows up). A younger one may really be in progress in
# another tab.
RUNNING_STALE_AFTER = timedelta(minutes=10)


class SessionService:
    def __init__(self, db: AsyncSession):
        self.repo = ChatRepository(db)

    async def get_sessions(self, session_ids: list[uuid.UUID]) -> list[SessionSummary]:
        """Metadata of the given sessions, most recently updated first. Unknown ids
        are left out."""
        sessions = await self.repo.get_sessions(session_ids)
        counts = await self.repo.count_messages([s.id for s in sessions])
        return [self._summary(s, counts.get(s.id, 0)) for s in sessions]

    async def get_session(self, session_id: uuid.UUID) -> SessionDetail:
        session = await self._session(session_id)
        messages = await self.repo.get_full_history(session_id)
        now = datetime.now(timezone.utc)
        return SessionDetail(
            id=session.id,
            title=session.title,
            updated_at=session.updated_at,
            messages=[self._message(m, now) for m in messages],
        )

    async def rename_session(self, session_id: uuid.UUID, title: str) -> SessionSummary:
        if not await self.repo.set_title(session_id, title, manual=True):
            raise SessionNotFoundException(f"Session {session_id} not found")
        session = await self._session(session_id)
        counts = await self.repo.count_messages([session_id])
        return self._summary(session, counts.get(session_id, 0))

    async def delete_session(self, session_id: uuid.UUID) -> None:
        if not await self.repo.delete_session(session_id):
            raise SessionNotFoundException(f"Session {session_id} not found")

    async def get_step_result(self, step_id: uuid.UUID) -> StepResult:
        stored = await self.repo.get_step_result(step_id)
        if stored is None:
            raise StepNotFoundException(f"Step {step_id} not found")
        return StepResult(step_id=step_id, kind=stored[0], result=stored[1])

    async def _session(self, session_id: uuid.UUID) -> ChatSession:
        sessions = await self.repo.get_sessions([session_id])
        if not sessions:
            raise SessionNotFoundException(f"Session {session_id} not found")
        return sessions[0]

    @staticmethod
    def _summary(session: ChatSession, message_count: int) -> SessionSummary:
        return SessionSummary(
            id=session.id,
            title=session.title,
            updated_at=session.updated_at,
            message_count=message_count,
        )

    @staticmethod
    def _message(m: Message, now: datetime) -> MessageOut:
        status = m.status
        if status == "running" and now - m.created_at > RUNNING_STALE_AFTER:
            status = "aborted"
        return MessageOut(
            id=m.id,
            turn=m.turn,
            role=m.role,  # type: ignore[arg-type]
            content=m.content,
            thinking=m.thinking,
            status=status,  # type: ignore[arg-type]
            created_at=m.created_at,
            steps=[
                StepOut(
                    id=s.id,
                    ordinal=s.ordinal,
                    kind=s.kind,
                    args=s.args,
                    thinking=s.thinking,
                    ok=s.ok,
                    count=s.count,
                    error=s.error,
                    duration_ms=s.duration_ms,
                )
                for s in m.steps
            ],
        )
