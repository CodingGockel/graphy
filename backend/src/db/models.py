import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB, UUID


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True once a user renamed the session; such a title is never overwritten.
    title_is_manual: Mapped[bool] = mapped_column(
        Boolean, server_default=false(), default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Bumped explicitly (ChatRepository.touch_session) when a turn completes.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_sessions_updated_at", text("updated_at DESC")),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # One turn = one user message + one assistant message with the same number.
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Assistant only: the reasoning before the final answer.
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    # running | complete | aborted | error. User messages are always complete.
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Never lazy-loaded (async): read queries load the steps explicitly.
    steps: Mapped[list["Step"]] = relationship(
        order_by="Step.ordinal", lazy="raise", passive_deletes=True
    )

    __table_args__ = (
        # Also the lookup index. A duplicate turn (two tabs sending in the same
        # session) fails loudly instead of corrupting the history.
        UniqueConstraint("session_id", "turn", "role", name="uq_messages_session_turn_role"),
    )


class Step(Base):
    """One tool call of an assistant message."""

    __tablename__ = "steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    # resolve_entity | sparql_query | previous_results | papers | clarification
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # The model's reasoning before this tool call.
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ok, count and duration_ms are NULL while the step runs.
    ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Rows (sparql_query, previous_results) or candidates (resolve_entity).
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Deferred: never loaded with a step, only via ChatRepository.get_step_result.
    result: Mapped[Any] = mapped_column(
        JSONB(none_as_null=True), nullable=True, deferred=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("message_id", "ordinal", name="uq_steps_message_ordinal"),
    )
