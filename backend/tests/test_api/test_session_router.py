import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from src.api.dependencies import get_session_service
from src.main import app
from src.models.schemas import (
    MessageOut,
    SessionDetail,
    SessionSummary,
    StepOut,
    StepResult,
)
from src.util.exceptions import SessionNotFoundException, StepNotFoundException

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def _override_session_service() -> MagicMock:
    service = MagicMock()
    app.dependency_overrides[get_session_service] = lambda: service
    return service


def _summary(session_id: uuid.UUID, title: str | None = "Title") -> SessionSummary:
    return SessionSummary(id=session_id, title=title, updated_at=NOW, message_count=2)


class TestGetSessions:
    def test_returns_metadata_for_the_given_ids(self, client):
        service = _override_session_service()
        a, b = uuid.uuid4(), uuid.uuid4()
        service.get_sessions = AsyncMock(return_value=[_summary(a)])

        resp = client.get(f"/api/v1/sessions?ids={a},{b}")

        assert resp.status_code == 200
        assert resp.json() == [
            {
                "id": str(a),
                "title": "Title",
                "updated_at": "2026-10-01T12:00:00Z",
                "message_count": 2,
            }
        ]
        service.get_sessions.assert_awaited_once_with([a, b])

    def test_duplicate_ids_are_passed_once(self, client):
        service = _override_session_service()
        a = uuid.uuid4()
        service.get_sessions = AsyncMock(return_value=[])

        resp = client.get(f"/api/v1/sessions?ids={a},{a}")

        assert resp.status_code == 200
        service.get_sessions.assert_awaited_once_with([a])

    def test_ids_are_required(self, client):
        _override_session_service()
        assert client.get("/api/v1/sessions").status_code == 422

    def test_empty_ids_are_422(self, client):
        _override_session_service()
        assert client.get("/api/v1/sessions?ids=").status_code == 422

    def test_invalid_id_is_422(self, client):
        _override_session_service()
        assert client.get("/api/v1/sessions?ids=not-a-uuid").status_code == 422

    def test_100_ids_are_accepted(self, client):
        service = _override_session_service()
        service.get_sessions = AsyncMock(return_value=[])
        ids = ",".join(str(uuid.uuid4()) for _ in range(100))

        assert client.get(f"/api/v1/sessions?ids={ids}").status_code == 200

    def test_more_than_100_ids_are_422(self, client):
        service = _override_session_service()
        service.get_sessions = AsyncMock(return_value=[])
        ids = ",".join(str(uuid.uuid4()) for _ in range(101))

        resp = client.get(f"/api/v1/sessions?ids={ids}")

        assert resp.status_code == 422
        service.get_sessions.assert_not_awaited()


class TestGetSession:
    def test_returns_messages_with_steps_but_without_results(self, client):
        service = _override_session_service()
        sid = uuid.uuid4()
        step = StepOut(
            id=uuid.uuid4(), ordinal=1, kind="sparql_query", args={"query": "SELECT"},
            thinking=None, ok=True, count=3, error=None, duration_ms=12,
        )
        service.get_session = AsyncMock(
            return_value=SessionDetail(
                id=sid,
                title=None,
                updated_at=NOW,
                messages=[
                    MessageOut(
                        id=uuid.uuid4(), turn=1, role="user", content="hi", thinking=None,
                        status="complete", created_at=NOW, steps=[],
                    ),
                    MessageOut(
                        id=uuid.uuid4(), turn=1, role="assistant", content="answer",
                        thinking=None, status="complete", created_at=NOW, steps=[step],
                    ),
                ],
            )
        )

        resp = client.get(f"/api/v1/sessions/{sid}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(sid)
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
        step_json = body["messages"][1]["steps"][0]
        assert step_json["count"] == 3
        assert "result" not in step_json

    def test_not_found_is_404(self, client):
        service = _override_session_service()
        service.get_session = AsyncMock(side_effect=SessionNotFoundException("nope"))

        resp = client.get(f"/api/v1/sessions/{uuid.uuid4()}")

        assert resp.status_code == 404

    def test_old_history_path_is_gone(self, client):
        _override_session_service()
        assert client.get(f"/api/v1/session/{uuid.uuid4()}/history").status_code == 404


class TestRenameSession:
    def test_rename_returns_the_metadata(self, client):
        service = _override_session_service()
        sid = uuid.uuid4()
        service.rename_session = AsyncMock(return_value=_summary(sid, "New"))

        resp = client.patch(f"/api/v1/sessions/{sid}", json={"title": "  New  "})

        assert resp.status_code == 200
        assert resp.json()["title"] == "New"
        # surrounding whitespace is removed
        service.rename_session.assert_awaited_once_with(sid, "New")

    def test_blank_title_is_422(self, client):
        service = _override_session_service()
        service.rename_session = AsyncMock()

        resp = client.patch(f"/api/v1/sessions/{uuid.uuid4()}", json={"title": "   "})

        assert resp.status_code == 422
        service.rename_session.assert_not_awaited()

    def test_too_long_title_is_422(self, client):
        _override_session_service()
        resp = client.patch(f"/api/v1/sessions/{uuid.uuid4()}", json={"title": "x" * 201})
        assert resp.status_code == 422

    def test_not_found_is_404(self, client):
        service = _override_session_service()
        service.rename_session = AsyncMock(side_effect=SessionNotFoundException("nope"))

        resp = client.patch(f"/api/v1/sessions/{uuid.uuid4()}", json={"title": "New"})

        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete_returns_204(self, client):
        service = _override_session_service()
        service.delete_session = AsyncMock(return_value=None)

        resp = client.delete(f"/api/v1/sessions/{uuid.uuid4()}")

        assert resp.status_code == 204

    def test_delete_missing_is_404(self, client):
        service = _override_session_service()
        service.delete_session = AsyncMock(
            side_effect=SessionNotFoundException("nope")
        )

        resp = client.delete(f"/api/v1/sessions/{uuid.uuid4()}")

        assert resp.status_code == 404


class TestGetStepResult:
    def test_returns_the_result(self, client):
        service = _override_session_service()
        step_id = uuid.uuid4()
        result = {"head": {"vars": ["x"]}, "results": {"bindings": []}}
        service.get_step_result = AsyncMock(
            return_value=StepResult(step_id=step_id, kind="sparql_query", result=result)
        )

        resp = client.get(f"/api/v1/steps/{step_id}/result")

        assert resp.status_code == 200
        assert resp.json() == {"step_id": str(step_id), "kind": "sparql_query", "result": result}

    def test_unknown_step_is_404(self, client):
        service = _override_session_service()
        service.get_step_result = AsyncMock(side_effect=StepNotFoundException("nope"))

        resp = client.get(f"/api/v1/steps/{uuid.uuid4()}/result")

        assert resp.status_code == 404
        assert resp.json()["error"] == "Step not found"
