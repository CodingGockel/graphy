import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.chat import ChatCompletionMessage

from src.models.events import (
    AnswerEvent,
    DoneEvent,
    SessionEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from src.models.schemas import ModelResponse
from src.services.chat_service import (
    DEFAULT_CLARIFICATION,
    NO_PREVIOUS_DATA_ANSWER,
    ChatService,
    TurnState,
)
from src.services.llm_service import LLMTurn, ToolCallResult
from src.util.exceptions import (
    SessionNotFoundException,
    SparqlDatabaseException,
    SparqlQueryException,
)
from tests.factories import make_db_message, make_db_step

QUERY = "SELECT ?s WHERE { ?s ?p ?o } LIMIT 5"
ONE_ROW = '{"results": {"bindings": [{"s": {"value": "x"}}]}}'


def _tool_turn(name: str, arguments: dict, call_id: str = "c1") -> LLMTurn:
    raw = ChatCompletionMessage(role="assistant", content=None)
    return LLMTurn(
        tool_call=ToolCallResult(call_id, name, arguments, raw),
        answer=None,
        raw_message=raw,
    )


def _answer_turn(text: str) -> LLMTurn:
    raw = ChatCompletionMessage(role="assistant", content=text)
    return LLMTurn(tool_call=None, answer=text, raw_message=raw)


@pytest.fixture
def repo():
    repo = AsyncMock()
    repo.create_session = AsyncMock(return_value=uuid.uuid4())
    repo.get_sessions = AsyncMock(return_value=[SimpleNamespace(title=None)])
    repo.get_history = AsyncMock(return_value=[])
    repo.start_turn = AsyncMock(side_effect=lambda *args, **kwargs: uuid.uuid4())
    repo.start_step = AsyncMock(side_effect=lambda *args, **kwargs: uuid.uuid4())
    repo.get_step_result = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def chat_service(settings_stub):
    llm = MagicMock()
    llm.query_system_prompt = MagicMock(return_value="SYSTEM PROMPT")
    llm.chat_with_tools = AsyncMock()
    llm.generate_answer = AsyncMock(return_value="final answer")
    llm.get_models = AsyncMock(return_value=ModelResponse(models={"m"}))

    sparql = MagicMock()
    sparql.execute = AsyncMock(return_value='{"results": {"bindings": []}}')

    lucene = MagicMock()
    lucene.search = AsyncMock(return_value=[])

    service = ChatService(llm=llm, sparql=sparql, lucene=lucene, settings=settings_stub)
    return service, llm, sparql, lucene


async def _run(service, repo, message="hi", session_id=None, state=None):
    """Consume a whole turn and return its events."""
    state = state if state is not None else TurnState()
    return [e async for e in service.run(session_id, message, repo, state)]


async def _run_until_error(service, repo, exc_type, state=None):
    """Consume a turn that is expected to fail; return the events seen before."""
    state = state if state is not None else TurnState()
    events = []
    with pytest.raises(exc_type):
        async for event in service.run(None, "hi", repo, state):
            events.append(event)
    return events


def _names(events) -> list[str]:
    return [e.event for e in events]


def _steps(events) -> list[tuple[StepStartedEvent, StepFinishedEvent]]:
    """Pair every step_started with its step_finished (by step id)."""
    finished = {e.step_id: e for e in events if isinstance(e, StepFinishedEvent)}
    return [(e, finished[e.step_id]) for e in events if isinstance(e, StepStartedEvent)]


def _answer(events) -> str:
    return "".join(e.delta for e in events if isinstance(e, AnswerEvent))


def _history_with_data(turn: int, step_id: uuid.UUID) -> list:
    return [
        make_db_message("user", "earlier question", turn=turn),
        make_db_message(
            "assistant",
            "earlier answer",
            turn=turn,
            steps=[
                make_db_step(args={"query": "SELECT ?failed {}"}, ok=False, ordinal=1),
                make_db_step(args={"query": "SELECT ?old {}"}, ordinal=2, step_id=step_id),
            ],
        ),
    ]


class TestSession:
    async def test_new_session_is_created_and_announced_first(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_answer_turn("Hello.")]

        state = TurnState()
        events = await _run(service, repo, state=state)

        first = events[0]
        assert isinstance(first, SessionEvent)
        assert first.session_id == repo.create_session.return_value
        assert first.title is None
        # message_id is the assistant message, also handed to the caller via the state
        assert first.message_id == state.message_id
        repo.get_sessions.assert_not_awaited()

    async def test_existing_session_is_reused(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_answer_turn("Hello.")]
        repo.get_sessions.return_value = [SimpleNamespace(title="Tulips")]
        sid = uuid.uuid4()

        events = await _run(service, repo, session_id=sid)

        assert events[0].session_id == sid
        assert events[0].title == "Tulips"
        repo.create_session.assert_not_awaited()

    async def test_unknown_session_raises_before_anything_is_written(self, chat_service, repo):
        service, llm, _, _ = chat_service
        repo.get_sessions.return_value = []

        with pytest.raises(SessionNotFoundException):
            await _run(service, repo, session_id=uuid.uuid4())

        repo.create_session.assert_not_awaited()
        repo.start_turn.assert_not_awaited()
        llm.chat_with_tools.assert_not_awaited()

    async def test_turn_is_opened_with_the_question(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_answer_turn("Hello.")]

        events = await _run(service, repo, message="my question")

        # Question and running answer are written together (ChatRepository.start_turn).
        repo.start_turn.assert_awaited_once_with(events[0].session_id, "my question")


class TestPlainAnswer:
    async def test_answer_without_a_query(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_answer_turn("Hello.")]

        state = TurnState()
        events = await _run(service, repo, state=state)

        assert _names(events) == ["session", "answer", "done"]
        assert _answer(events) == "Hello."
        assert state.answer == "Hello."
        # No data was gathered, so the loop text is the answer.
        llm.generate_answer.assert_not_awaited()
        repo.start_step.assert_not_awaited()

        done = events[-1]
        assert isinstance(done, DoneEvent)
        assert done.message_id == state.message_id
        assert done.row_count is None

    async def test_message_is_completed_and_session_touched(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_answer_turn("Hello.")]

        state = TurnState()
        events = await _run(service, repo, state=state)

        # Answer and session timestamp are stored together (ChatRepository.complete_turn).
        repo.complete_turn.assert_awaited_once_with(
            events[0].session_id, state.message_id, content="Hello.", thinking=None
        )
        repo.fail_message.assert_not_awaited()


class TestQuery:
    async def test_one_query(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            _answer_turn("loop text, not used"),
        ]
        sparql.execute.return_value = ONE_ROW

        events = await _run(service, repo, message="my question")

        assert _names(events) == ["session", "step_started", "step_finished", "answer", "done"]
        [(started, finished)] = _steps(events)
        assert (started.ordinal, started.kind, started.args) == (1, "sparql_query", {"query": QUERY})
        assert (finished.ok, finished.count, finished.error) == (True, 1, None)
        # The answer comes from the dedicated answer call, as one event.
        assert _answer(events) == "final answer"
        llm.generate_answer.assert_awaited_once_with("my question", QUERY, ONE_ROW)
        assert events[-1].row_count == 1

    async def test_step_is_persisted_with_its_result(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            _answer_turn("done"),
        ]
        sparql.execute.return_value = ONE_ROW

        state = TurnState()
        events = await _run(service, repo, state=state)

        start = repo.start_step.await_args
        assert start.args[0] == state.message_id
        assert start.kwargs == {"ordinal": 1, "kind": "sparql_query", "args": {"query": QUERY}}

        [(started, _)] = _steps(events)
        finish = repo.finish_step.await_args
        assert finish.args[0] == started.step_id
        assert finish.kwargs["ok"] is True
        assert finish.kwargs["count"] == 1
        # stored as parsed JSON; never part of an event
        assert finish.kwargs["result"] == {"results": {"bindings": [{"s": {"value": "x"}}]}}
        assert finish.kwargs["error"] is None

    async def test_missing_limit_is_added(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT ?s WHERE { ?s ?p ?o }"}),
            _answer_turn("done"),
        ]

        events = await _run(service, repo)

        [(started, _)] = _steps(events)
        assert started.args["query"].endswith("LIMIT 200")  # ensure_limit safety net
        assert sparql.execute.await_args.args[0] == started.args["query"]

    async def test_bad_query_then_corrected_query(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT bad LIMIT 1"}),
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            _answer_turn("recovered"),
        ]
        sparql.execute.side_effect = [SparqlQueryException("syntax error"), ONE_ROW]

        events = await _run(service, repo)

        assert _names(events) == [
            "session",
            "step_started", "step_finished",
            "step_started", "step_finished",
            "answer", "done",
        ]
        (first_start, first_end), (second_start, second_end) = _steps(events)
        assert (first_start.ordinal, second_start.ordinal) == (1, 2)
        assert first_end.ok is False
        assert first_end.error == "syntax error"
        assert first_end.count is None
        assert second_end.ok is True
        assert _answer(events) == "final answer"

        # The failed step is stored as failed, without a result ...
        failed = repo.finish_step.await_args_list[0].kwargs
        assert (failed["ok"], failed["result"], failed["error"]) == (False, None, "syntax error")
        # ... and the error went back to the model (the transcript is one growing list).
        transcript = llm.chat_with_tools.await_args.args[0]
        feedback = [m["content"] for m in transcript if "FAILED" in str(m.get("content"))]
        assert len(feedback) == 1
        assert "syntax error" in feedback[0]

    async def test_last_query_feeds_the_answer(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT ?a WHERE {} LIMIT 1"}),
            _tool_turn("execute_sparql_query", {"query": "SELECT ?b WHERE {} LIMIT 1"}),
            _answer_turn("done"),
        ]

        await _run(service, repo)

        # every query is a step now, not only the last one
        assert repo.start_step.await_count == 2
        assert "?b" in llm.generate_answer.await_args.args[1]


class TestResolveEntity:
    async def test_candidates_are_fed_back(self, chat_service, repo):
        service, llm, _, lucene = chat_service
        candidates = [{"uri": "http://x/1", "label": "Rose", "score": 2.0}]
        lucene.search.return_value = candidates
        llm.chat_with_tools.side_effect = [
            _tool_turn("resolve_entity", {"term": "rose", "type": "Species"}),
            _answer_turn("Roses found."),
        ]

        events = await _run(service, repo)

        assert _names(events) == ["session", "step_started", "step_finished", "answer", "done"]
        [(started, finished)] = _steps(events)
        assert started.kind == "resolve_entity"
        assert started.args == {"term": "rose", "type": "Species", "limit": 5}
        assert (finished.ok, finished.count) == (True, 1)
        lucene.search.assert_awaited_once_with("rose", "Species", 5)
        # the candidates are the stored result
        assert repo.finish_step.await_args.kwargs["result"] == candidates
        # No query was executed, so the loop's own answer text is the answer.
        assert _answer(events) == "Roses found."
        llm.generate_answer.assert_not_awaited()

    async def test_without_lucene_connector_the_step_fails_and_the_loop_goes_on(
        self, chat_service, repo
    ):
        service, llm, _, lucene = chat_service
        lucene.search.side_effect = SparqlQueryException("no connector")
        llm.chat_with_tools.side_effect = [
            _tool_turn("resolve_entity", {"term": "rose"}),
            _answer_turn("Could not look it up."),
        ]

        events = await _run(service, repo)

        [(_, finished)] = _steps(events)
        assert (finished.ok, finished.error) == (False, "no connector")
        fallback = llm.chat_with_tools.await_args_list[1].args[0][-1]["content"]
        assert "Entity resolution is unavailable" in fallback
        assert _answer(events) == "Could not look it up."


class TestUsePreviousResults:
    async def test_reuses_prior_turn_results(self, chat_service, repo):
        service, llm, _, _ = chat_service
        step_id = uuid.uuid4()
        # The turn map is keyed on messages.turn, not on the position in the window.
        repo.get_history.return_value = _history_with_data(7, step_id)
        repo.get_step_result.return_value = (
            "sparql_query", {"results": {"bindings": [{"v": {"value": "1"}}]}}
        )
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 7}),
            _answer_turn("reused"),
        ]

        events = await _run(service, repo, message="and again")

        [(started, finished)] = _steps(events)
        assert started.kind == "previous_results"
        # the step points at the step that holds the data
        assert started.args == {
            "reference_turn": 7,
            "source_step_id": str(step_id),
            "query": "SELECT ?old {}",
        }
        assert (finished.ok, finished.count) == (True, 1)
        repo.get_step_result.assert_awaited_once_with(step_id)
        # the result is not stored a second time
        assert repo.finish_step.await_args.kwargs["result"] is None

        question, query, results = llm.generate_answer.await_args.args
        assert (question, query) == ("and again", "SELECT ?old {}")
        assert '"value": "1"' in results
        assert events[-1].row_count == 1

    async def test_unknown_turn_falls_back_to_latest(self, chat_service, repo):
        service, llm, _, _ = chat_service
        step_id = uuid.uuid4()
        repo.get_history.return_value = _history_with_data(7, step_id)
        repo.get_step_result.return_value = ("sparql_query", {"results": {"bindings": []}})
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 1}),
            _answer_turn("reused"),
        ]

        events = await _run(service, repo)

        [(started, _)] = _steps(events)
        assert started.args["reference_turn"] == 7  # the resolved turn
        repo.get_step_result.assert_awaited_once_with(step_id)

    async def test_without_data_the_step_fails_and_a_fixed_answer_ends_the_turn(
        self, chat_service, repo
    ):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 1}),
        ]

        events = await _run(service, repo)

        assert _names(events) == ["session", "step_started", "step_finished", "answer", "done"]
        [(started, finished)] = _steps(events)
        assert started.args == {"reference_turn": 1}
        assert finished.ok is False
        assert finished.error
        assert _answer(events) == NO_PREVIOUS_DATA_ANSWER
        assert llm.chat_with_tools.await_count == 1
        llm.generate_answer.assert_not_awaited()
        repo.complete_turn.assert_awaited_once()

    async def test_reused_data_stays_reusable_in_later_turns(self, chat_service, repo):
        service, llm, _, _ = chat_service
        source_step = uuid.uuid4()
        # Turn 8 only reused the data of a turn that has left the history window.
        repo.get_history.return_value = [
            make_db_message("user", "follow-up", turn=8),
            make_db_message(
                "assistant",
                "reused answer",
                turn=8,
                steps=[
                    make_db_step(
                        kind="previous_results",
                        args={
                            "reference_turn": 7,
                            "source_step_id": str(source_step),
                            "query": "SELECT ?old {}",
                        },
                    )
                ],
            ),
        ]
        repo.get_step_result.return_value = ("sparql_query", {"results": {"bindings": []}})
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 8}),
            _answer_turn("reused"),
        ]

        events = await _run(service, repo)

        [(started, finished)] = _steps(events)
        assert finished.ok is True
        assert started.args == {
            "reference_turn": 8,
            "source_step_id": str(source_step),
            "query": "SELECT ?old {}",
        }
        repo.get_step_result.assert_awaited_once_with(source_step)
        assert llm.generate_answer.await_args.args[1] == "SELECT ?old {}"

    async def test_reusable_turns_are_listed_in_the_system_prompt(self, chat_service, repo):
        service, llm, _, _ = chat_service
        repo.get_history.return_value = _history_with_data(7, uuid.uuid4())
        llm.chat_with_tools.side_effect = [_answer_turn("ok")]

        await _run(service, repo)

        system_prompt = llm.chat_with_tools.await_args.args[0][0]["content"]
        assert "Turn 7: SELECT ?old {}" in system_prompt


class TestPapers:
    async def test_papers_step_has_no_result(self, chat_service, repo, mocker):
        service, llm, _, _ = chat_service
        mocker.patch(
            "src.services.chat_service._load_phenobs_papers_content", return_value="PAPERS"
        )
        llm.chat_with_tools.side_effect = [
            _tool_turn("load_phenobs_papers", {}),
            _answer_turn("From the papers."),
        ]

        events = await _run(service, repo)

        [(started, finished)] = _steps(events)
        assert (started.kind, started.args) == ("papers", {})
        assert (finished.ok, finished.count) == (True, None)
        assert repo.finish_step.await_args.kwargs["result"] is None
        assert llm.chat_with_tools.await_args_list[1].args[0][-1]["content"] == "PAPERS"
        assert _answer(events) == "From the papers."


class TestClarification:
    async def test_question_is_the_answer_and_ends_the_loop(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("ask_clarification", {"question": "Which species?"}),
        ]

        events = await _run(service, repo)

        assert _names(events) == ["session", "step_started", "step_finished", "answer", "done"]
        [(started, finished)] = _steps(events)
        assert (started.kind, started.args) == ("clarification", {"question": "Which species?"})
        assert finished.ok is True
        assert _answer(events) == "Which species?"
        assert llm.chat_with_tools.await_count == 1
        llm.generate_answer.assert_not_awaited()

    async def test_clarification_after_a_query_carries_no_row_count(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        sparql.execute.return_value = ONE_ROW
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            _tool_turn("ask_clarification", {"question": "Which year?"}),
        ]

        events = await _run(service, repo)

        assert _answer(events) == "Which year?"
        assert events[-1].row_count is None
        llm.generate_answer.assert_not_awaited()

    async def test_unknown_tool_is_treated_as_clarification(self, chat_service, repo):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_tool_turn("made_up_tool", {"x": 1})]

        events = await _run(service, repo)

        [(started, _)] = _steps(events)
        assert started.kind == "clarification"
        assert _answer(events) == DEFAULT_CLARIFICATION


class TestIterationCap:
    async def test_forces_answer_when_loop_exhausted(self, chat_service, repo):
        service, llm, _, _ = chat_service
        service.settings.chat_max_tool_iterations = 2
        llm.chat_with_tools.return_value = _tool_turn("execute_sparql_query", {"query": QUERY})

        events = await _run(service, repo)

        assert llm.chat_with_tools.await_count == 2
        assert [s.ordinal for s, _ in _steps(events)] == [1, 2]
        llm.generate_answer.assert_awaited_once()
        assert _answer(events) == "final answer"
        assert _names(events)[-1] == "done"


class TestFailures:
    async def test_infrastructure_error_marks_message_and_keeps_steps(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            _tool_turn("execute_sparql_query", {"query": QUERY}),
        ]
        sparql.execute.side_effect = [ONE_ROW, SparqlDatabaseException("graphdb down")]

        state = TurnState()
        events = await _run_until_error(service, repo, SparqlDatabaseException, state)

        # Both steps are closed: the earlier one ok, the failing one with the error.
        assert _names(events) == [
            "session", "step_started", "step_finished", "step_started", "step_finished",
        ]
        first, second = [c.kwargs for c in repo.finish_step.await_args_list]
        assert first["ok"] is True
        assert (second["ok"], second["error"]) == (False, "graphdb down")
        assert events[-1].ok is False

        repo.fail_message.assert_awaited_once_with(state.message_id, content="")
        repo.complete_turn.assert_not_awaited()

    async def test_unexpected_step_error_is_not_shown(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [_tool_turn("execute_sparql_query", {"query": QUERY})]
        sparql.execute.side_effect = RuntimeError("secret detail")

        events = await _run_until_error(service, repo, RuntimeError)

        # Stored and sent: only a domain exception shows its message.
        assert repo.finish_step.await_args.kwargs["error"] == "Internal server error"
        assert events[-1].error == "Internal server error"

    async def test_failing_to_close_the_step_does_not_hide_the_original_error(
        self, chat_service, repo
    ):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [_tool_turn("execute_sparql_query", {"query": QUERY})]
        sparql.execute.side_effect = SparqlDatabaseException("graphdb down")
        repo.finish_step.side_effect = ConnectionError("db gone")

        events = await _run_until_error(service, repo, SparqlDatabaseException)

        # The step is still reported as finished, and the message is marked.
        assert _names(events) == ["session", "step_started", "step_finished"]
        repo.fail_message.assert_awaited_once()

    async def test_unexpected_exception_marks_message_as_error_too(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            RuntimeError("a bug"),
        ]
        sparql.execute.return_value = ONE_ROW

        events = await _run_until_error(service, repo, RuntimeError)

        assert _names(events) == ["session", "step_started", "step_finished"]
        assert repo.finish_step.await_args.kwargs["ok"] is True
        repo.fail_message.assert_awaited_once()
        # a DB error may have left the transaction aborted
        repo.rollback.assert_awaited_once()

    async def test_failure_of_the_answer_call_marks_message_as_error(self, chat_service, repo):
        service, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": QUERY}),
            _answer_turn("done"),
        ]
        llm.generate_answer.side_effect = RuntimeError("llm down")

        events = await _run_until_error(service, repo, RuntimeError)

        assert "answer" not in _names(events)
        repo.fail_message.assert_awaited_once()

    async def test_failing_to_mark_the_message_does_not_hide_the_original_error(
        self, chat_service, repo
    ):
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = RuntimeError("a bug")
        repo.fail_message.side_effect = ConnectionError("db gone")

        await _run_until_error(service, repo, RuntimeError)


class TestHistory:
    async def test_history_is_sent_to_the_llm(self, chat_service, repo):
        service, llm, _, _ = chat_service
        repo.get_history.return_value = [
            make_db_message("user", "q1", turn=1),
            make_db_message("assistant", "a1", turn=1),
        ]
        llm.chat_with_tools.side_effect = [_answer_turn("ok")]

        await _run(service, repo, message="q2")

        sent = llm.chat_with_tools.await_args.args[0]
        assert [(m["role"], m["content"]) for m in sent[1:]] == [
            ("user", "q1"), ("assistant", "a1"), ("user", "q2"),
        ]

    async def test_reasoning_of_an_earlier_answer_is_not_sent_back(self, chat_service, repo):
        service, llm, _, _ = chat_service
        repo.get_history.return_value = [
            make_db_message("user", "q1", turn=1),
            make_db_message("assistant", "<think>let me see</think>a1", turn=1),
        ]
        llm.chat_with_tools.side_effect = [_answer_turn("ok")]

        await _run(service, repo, message="q2")

        sent = llm.chat_with_tools.await_args.args[0]
        assert sent[2] == {"role": "assistant", "content": "a1"}

    async def test_only_complete_turns_are_requested(self, chat_service, repo):
        # Non-complete turns are filtered by the repository (get_history returns
        # complete turns only); the service must not read the history any other way.
        service, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [_answer_turn("ok")]
        sid = uuid.uuid4()

        await _run(service, repo, session_id=sid)

        repo.get_history.assert_awaited_once_with(sid, turns=service.settings.chat_history_depth)
        repo.get_full_history.assert_not_awaited()


class TestModels:
    async def test_delegates_to_llm(self, chat_service):
        service, llm, _, _ = chat_service
        result = await service.models()
        assert result.models == {"m"}
        llm.get_models.assert_awaited_once()


class TestGetFullTable:
    async def test_parses_table(self, chat_service, mocker, sparql_results_json):
        service, _, sparql, _ = chat_service
        mocker.patch(
            "src.services.chat_service.load_prompt",
            return_value="SELECT ?name ?count WHERE { ?s ?p ?o }",
        )
        sparql.execute.return_value = sparql_results_json

        resp = await service.get_full_table(limit=None)

        assert resp.full_table.columns == ["name", "count"]
        assert resp.full_table.rows[0] == {"name": "Rose", "count": 5}

    async def test_appends_limit(self, chat_service, mocker, sparql_results_json):
        service, _, sparql, _ = chat_service
        mocker.patch(
            "src.services.chat_service.load_prompt",
            return_value="SELECT ?name ?count WHERE { ?s ?p ?o }",
        )
        sparql.execute.return_value = sparql_results_json

        await service.get_full_table(limit=10)

        sent_query = sparql.execute.await_args.args[0]
        assert sent_query.endswith("LIMIT 10")
