"""ChatRepository against a mocked AsyncSession: checks the shape of the statements
and that every method ends its transaction. No database involved."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from src.db.models import Message, Step
from src.db.repository import ChatRepository, reusable_data
from tests.factories import make_db_message, make_db_step


def _make_repo(*, rows=None, scalar=None, row=None, rowcount=1):
    """A repository whose session returns one canned result for any statement."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows if rows is not None else []
    result.scalar_one.return_value = scalar
    result.scalar_one_or_none.return_value = scalar
    result.one_or_none.return_value = row
    result.rowcount = rowcount

    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()
    return ChatRepository(session), session


def _sql(session) -> tuple[str, dict]:
    """The (only) executed statement as PostgreSQL text plus its bound parameters."""
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


class TestSchema:
    def test_step_result_is_deferred(self):
        # Loading a step (e.g. with the history) must never pull its result.
        assert inspect(Step).column_attrs["result"].deferred is True

    def test_step_result_is_never_lazy_loaded(self):
        # An accidental access fails clearly instead of triggering a lazy load.
        assert inspect(Step).column_attrs["result"].raiseload is True

    def test_steps_are_never_lazy_loaded(self):
        assert inspect(Message).relationships["steps"].lazy == "raise"

    def test_unique_constraints(self):
        def unique_columns(model):
            return {
                tuple(col.name for col in constraint.columns)
                for constraint in model.__table__.constraints
                if type(constraint).__name__ == "UniqueConstraint"
            }

        assert ("session_id", "turn", "role") in unique_columns(Message)
        assert ("message_id", "ordinal") in unique_columns(Step)


class TestGetHistory:
    async def test_only_complete_turns_limited_to_depth(self):
        repo, session = _make_repo()

        await repo.get_history(uuid.uuid4(), turns=3)

        sql, params = _sql(session)
        assert "messages.status" in sql
        assert "LIMIT" in sql
        assert "ORDER BY messages.turn DESC" in sql
        assert "complete" in params.values()
        assert "assistant" in params.values()
        assert 3 in params.values()

    async def test_step_results_are_not_selected(self):
        repo, session = _make_repo()

        await repo.get_history(uuid.uuid4(), turns=3)

        sql, _ = _sql(session)
        assert "result" not in sql

    async def test_returns_turn_order_with_user_first(self):
        rows = [
            make_db_message("assistant", "a2", turn=2),
            make_db_message("user", "q2", turn=2),
            make_db_message("assistant", "a1", turn=1),
            make_db_message("user", "q1", turn=1),
        ]
        repo, _ = _make_repo(rows=rows)

        messages = await repo.get_history(uuid.uuid4(), turns=5)

        assert [m.content for m in messages] == ["q1", "a1", "q2", "a2"]


class TestGetFullHistory:
    async def test_returns_everything_in_turn_order(self):
        rows = [
            make_db_message("user", "q2", turn=2),
            make_db_message("assistant", "a1", turn=1, status="error"),
            make_db_message("user", "q1", turn=1),
        ]
        repo, session = _make_repo(rows=rows)

        messages = await repo.get_full_history(uuid.uuid4())

        assert [m.content for m in messages] == ["q1", "a1", "q2"]
        sql, _ = _sql(session)
        assert "status" not in sql.split("WHERE")[1]
        assert "LIMIT" not in sql


class TestStartTurn:
    async def test_writes_question_and_running_answer_in_one_transaction(self):
        repo, session = _make_repo(scalar=4)
        sid = uuid.uuid4()

        message_id = await repo.start_turn(sid, "my question")

        user, assistant = session.add_all.call_args.args[0]
        assert (user.role, user.turn, user.status, user.content) == (
            "user", 5, "complete", "my question",
        )
        assert (assistant.role, assistant.turn, assistant.status) == ("assistant", 5, "running")
        assert user.session_id == assistant.session_id == sid
        assert assistant.id == message_id
        session.commit.assert_awaited_once()

    async def test_first_turn_is_one(self):
        repo, session = _make_repo(scalar=0)  # coalesce(max(turn), 0)

        await repo.start_turn(uuid.uuid4(), "hi")

        assert session.add_all.call_args.args[0][0].turn == 1
        assert "coalesce" in _sql(session)[0].lower()


class TestGetStepResult:
    async def test_returns_kind_and_result(self):
        repo, session = _make_repo(row=("sparql_query", {"results": {"bindings": []}}))

        stored = await repo.get_step_result(uuid.uuid4())

        assert stored == ("sparql_query", {"results": {"bindings": []}})
        sql, _ = _sql(session)
        assert "steps.result" in sql

    async def test_unknown_step_is_none(self):
        repo, _ = _make_repo(row=None)
        assert await repo.get_step_result(uuid.uuid4()) is None


class TestWrites:
    async def test_complete_turn_stores_the_answer_and_touches_the_session(self):
        repo, session = _make_repo()

        await repo.complete_turn(uuid.uuid4(), uuid.uuid4(), content="answer", thinking=None)

        statements = [
            str(c.args[0].compile(dialect=postgresql.dialect()))
            for c in session.execute.await_args_list
        ]
        assert statements[0].startswith("UPDATE messages")
        assert statements[1].startswith("UPDATE sessions")
        assert "updated_at" in statements[1]
        # one transaction for both
        session.commit.assert_awaited_once()

    async def test_fail_message_only_touches_a_running_message(self):
        repo, session = _make_repo()

        await repo.fail_message(uuid.uuid4(), content="partial")

        sql, params = _sql(session)
        assert "messages.status" in sql.split("WHERE")[1]
        assert {"running", "error", "partial"} <= set(params.values())

    async def test_start_step_returns_the_new_id(self):
        repo, session = _make_repo()

        step_id = await repo.start_step(
            uuid.uuid4(), ordinal=2, kind="sparql_query", args={"query": "ASK {}"}
        )

        added = session.add.call_args.args[0]
        assert isinstance(added, Step)
        assert added.id == step_id
        assert (added.ordinal, added.kind, added.ok) == (2, "sparql_query", None)

    async def test_abort_message_only_touches_a_running_message(self):
        repo, session = _make_repo()

        await repo.abort_message(uuid.uuid4(), content="partial", thinking=None)

        sql, params = _sql(session)
        assert "messages.status" in sql.split("WHERE")[1]
        assert {"running", "aborted", "partial"} <= set(params.values())

    async def test_set_title_reports_whether_the_session_existed(self):
        repo, _ = _make_repo(rowcount=0)
        assert await repo.set_title(uuid.uuid4(), "Title", manual=True) is False

    async def test_generated_title_never_replaces_a_manual_one(self):
        repo, session = _make_repo(rowcount=0)

        assert await repo.set_title(uuid.uuid4(), "Generated", manual=False) is False

        assert "title_is_manual" in _sql(session)[0].split("WHERE")[1]

    async def test_manual_title_replaces_any_title(self):
        repo, session = _make_repo()

        assert await repo.set_title(uuid.uuid4(), "Mine", manual=True) is True

        assert "title_is_manual" not in _sql(session)[0].split("WHERE")[1]

    async def test_count_messages_maps_sessions_to_counts(self):
        repo, session = _make_repo()
        a, b = uuid.uuid4(), uuid.uuid4()
        session.execute.return_value.all.return_value = [(a, 4), (b, 2)]

        assert await repo.count_messages([a, b]) == {a: 4, b: 2}

        sql, _ = _sql(session)
        assert "GROUP BY messages.session_id" in sql

    async def test_count_messages_without_ids_does_not_query(self):
        repo, session = _make_repo()
        assert await repo.count_messages([]) == {}
        session.execute.assert_not_awaited()

    async def test_get_sessions_without_ids_does_not_query(self):
        repo, session = _make_repo()
        assert await repo.get_sessions([]) == []
        session.execute.assert_not_awaited()


class TestTransactions:
    """Reads included: no method may leave its transaction open."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda r: r.create_session(),
            lambda r: r.session_exists(uuid.uuid4()),
            lambda r: r.get_sessions([uuid.uuid4()]),
            lambda r: r.count_messages([uuid.uuid4()]),
            lambda r: r.set_title(uuid.uuid4(), "t", manual=False),
            lambda r: r.delete_session(uuid.uuid4()),
            lambda r: r.start_turn(uuid.uuid4(), "hi"),
            lambda r: r.complete_turn(uuid.uuid4(), uuid.uuid4(), "answer", None),
            lambda r: r.fail_message(uuid.uuid4(), "partial"),
            lambda r: r.abort_message(uuid.uuid4(), "partial", None),
            lambda r: r.start_step(uuid.uuid4(), 1, "papers", {}),
            lambda r: r.finish_step(uuid.uuid4(), True, None, None, None, 5),
            lambda r: r.get_step_result(uuid.uuid4()),
            lambda r: r.get_history(uuid.uuid4(), turns=3),
            lambda r: r.get_full_history(uuid.uuid4()),
        ],
    )
    async def test_method_commits(self, call):
        repo, session = _make_repo(scalar=0)
        await call(repo)
        session.commit.assert_awaited_once()


class TestRollback:
    async def test_rolls_the_session_back(self):
        repo, session = _make_repo()
        session.rollback = AsyncMock()
        await repo.rollback()
        session.rollback.assert_awaited_once()


class TestReusableData:
    def test_picks_the_last_successful_query_step(self):
        wanted = make_db_step(args={"query": "B"}, ordinal=2)
        message = make_db_message(
            "assistant",
            "answer",
            steps=[
                make_db_step(args={"query": "A"}, ordinal=1),
                wanted,
                make_db_step(args={"query": "C"}, ok=False, ordinal=3),
                make_db_step(kind="resolve_entity", ordinal=4),
            ],
        )
        assert reusable_data(message) == (wanted.id, "B")

    def test_follows_a_previous_results_step_to_its_source(self):
        source = uuid.uuid4()
        message = make_db_message(
            "assistant",
            "answer",
            steps=[
                make_db_step(
                    kind="previous_results",
                    args={"reference_turn": 3, "source_step_id": str(source), "query": "Q"},
                )
            ],
        )
        assert reusable_data(message) == (source, "Q")

    def test_ignores_a_previous_results_step_without_a_source(self):
        message = make_db_message(
            "assistant",
            "answer",
            steps=[
                make_db_step(kind="previous_results", args={"reference_turn": 3}),
                make_db_step(kind="previous_results", args={"source_step_id": "x"}),
                make_db_step(
                    kind="previous_results", args={"source_step_id": str(uuid.uuid4())}, ok=False
                ),
            ],
        )
        assert reusable_data(message) is None

    def test_none_without_a_successful_query(self):
        message = make_db_message(
            "assistant", "answer", steps=[make_db_step(ok=False), make_db_step(kind="papers")]
        )
        assert reusable_data(message) is None
