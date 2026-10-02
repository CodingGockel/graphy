import json
import uuid

import pytest
from pydantic import ValidationError

from src.models.events import (
    SSE_PING,
    AnswerEvent,
    DoneEvent,
    ErrorEvent,
    SessionEvent,
    SessionTitleEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ThinkingEvent,
    encode_sse,
)

SID = uuid.uuid4()
MID = uuid.uuid4()
STEP = uuid.uuid4()


def _parse(frame: str) -> tuple[str, dict]:
    """Split one SSE frame into its event name and decoded data."""
    assert frame.endswith("\n\n")
    lines = frame[:-2].split("\n")
    assert len(lines) == 2, "a frame is exactly one event line and one data line"
    assert lines[0].startswith("event: ")
    assert lines[1].startswith("data: ")
    return lines[0][len("event: "):], json.loads(lines[1][len("data: "):])


class TestFraming:
    @pytest.mark.parametrize(
        "event, name, data",
        [
            (
                SessionEvent(session_id=SID, message_id=MID, title=None),
                "session",
                {"session_id": str(SID), "message_id": str(MID), "title": None},
            ),
            (
                SessionTitleEvent(session_id=SID, title="Flowering of Tulipa"),
                "session_title",
                {"session_id": str(SID), "title": "Flowering of Tulipa"},
            ),
            (
                StepStartedEvent(
                    step_id=STEP, ordinal=1, kind="resolve_entity", args={"term": "rose"}
                ),
                "step_started",
                {
                    "step_id": str(STEP),
                    "ordinal": 1,
                    "kind": "resolve_entity",
                    "args": {"term": "rose"},
                },
            ),
            (
                StepFinishedEvent(step_id=STEP, ok=True, count=3, duration_ms=412),
                "step_finished",
                {"step_id": str(STEP), "ok": True, "count": 3, "error": None, "duration_ms": 412},
            ),
            (
                StepFinishedEvent(step_id=STEP, ok=False, error="syntax error", duration_ms=7),
                "step_finished",
                {
                    "step_id": str(STEP),
                    "ok": False,
                    "count": None,
                    "error": "syntax error",
                    "duration_ms": 7,
                },
            ),
            (ThinkingEvent(delta="The user means"), "thinking", {"delta": "The user means"}),
            (AnswerEvent(delta="Tulipa "), "answer", {"delta": "Tulipa "}),
            (
                DoneEvent(message_id=MID, row_count=42),
                "done",
                {"message_id": str(MID), "row_count": 42},
            ),
            (
                DoneEvent(message_id=MID),
                "done",
                {"message_id": str(MID), "row_count": None},
            ),
            (
                ErrorEvent(kind="llm_unavailable", message="connection refused"),
                "error",
                {"kind": "llm_unavailable", "message": "connection refused"},
            ),
        ],
    )
    def test_each_event(self, event, name, data):
        # Exact equality also proves that `event` is not repeated inside `data`.
        assert _parse(encode_sse(event)) == (name, data)

    def test_non_ascii_text_stays_on_one_line(self):
        text = "Blütezeit: 27. März\nSchneeglöckchen — «früh»\r\n日本"
        frame = encode_sse(AnswerEvent(delta=text))

        name, data = _parse(frame)  # asserts the single data line
        assert name == "answer"
        assert data["delta"] == text
        # Non-ASCII is sent as UTF-8, not as \u escapes.
        assert "Blütezeit" in frame

    def test_ping_is_a_comment_frame(self):
        assert SSE_PING.startswith(":")
        assert SSE_PING.endswith("\n\n")


class TestValidation:
    def test_unknown_step_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            StepStartedEvent(step_id=STEP, ordinal=1, kind="made_up", args={})

    def test_unknown_error_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            ErrorEvent(kind="made_up", message="x")
