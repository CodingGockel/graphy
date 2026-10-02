import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.chat import ChatCompletionMessage

from src.models.schemas import ChatRequest, ModelResponse
from src.services.chat_service import ChatService
from src.services.llm_service import LLMTurn, ToolCallResult
from src.util.exceptions import SparqlQueryException
from tests.factories import make_db_message, make_db_step


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
def chat_service(mocker, settings_stub):
    repo = AsyncMock()
    repo.create_session = AsyncMock(return_value=uuid.uuid4())
    repo.session_exists = AsyncMock(return_value=True)
    repo.get_history = AsyncMock(return_value=[])
    repo.next_turn = AsyncMock(return_value=1)
    repo.add_message = AsyncMock(side_effect=lambda **kwargs: uuid.uuid4())
    repo.start_step = AsyncMock(return_value=uuid.uuid4())
    repo.get_step_result = AsyncMock(return_value=None)
    mocker.patch("src.services.chat_service.ChatRepository", return_value=repo)

    llm = MagicMock()
    llm.query_system_prompt = MagicMock(return_value="SYSTEM PROMPT")
    llm.chat_with_tools = AsyncMock()
    llm.generate_answer = AsyncMock(return_value="final answer")
    llm.get_models = AsyncMock(return_value=ModelResponse(models={"m"}))

    sparql = MagicMock()
    sparql.execute = AsyncMock(return_value='{"results": {"bindings": []}}')

    lucene = MagicMock()
    lucene.search = AsyncMock(return_value=[])

    service = ChatService(
        llm=llm, sparql=sparql, lucene=lucene, db=MagicMock(), settings=settings_stub
    )
    return service, repo, llm, sparql, lucene


class TestProcessExecuteQuery:
    async def test_runs_query_then_final_answer(self, chat_service):
        service, repo, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT ?s WHERE { ?s ?p ?o }"}),
            _answer_turn("done"),
        ]
        sparql.execute.return_value = '{"results": {"bindings": [{"s": {"value": "x"}}]}}'

        resp = await service.process(ChatRequest(message="hi"))

        assert resp.answer == "final answer"
        assert "SELECT" in resp.llm_generated_query
        assert "LIMIT 200" in resp.llm_generated_query  # ensure_limit safety net
        llm.generate_answer.assert_awaited_once()

    async def test_persists_messages_and_one_step(self, chat_service):
        service, repo, llm, sparql, _ = chat_service
        repo.next_turn.return_value = 3
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT ?s WHERE { ?s ?p ?o }"}),
            _answer_turn("done"),
        ]
        sparql.execute.return_value = '{"results": {"bindings": [{"s": {"value": "x"}}]}}'

        await service.process(ChatRequest(message="hi"))

        # user message, then the assistant message of the same turn
        user, assistant = [c.kwargs for c in repo.add_message.await_args_list]
        assert (user["role"], user["turn"], user["status"]) == ("user", 3, "complete")
        assert (assistant["role"], assistant["turn"]) == ("assistant", 3)

        start = repo.start_step.await_args
        assert start.kwargs["kind"] == "sparql_query"
        assert start.kwargs["ordinal"] == 1
        assert "LIMIT 200" in start.kwargs["args"]["query"]

        finish = repo.finish_step.await_args
        assert finish.args[0] == repo.start_step.return_value
        assert finish.kwargs["ok"] is True
        assert finish.kwargs["count"] == 1
        # stored as parsed JSON, not as the raw string
        assert finish.kwargs["result"] == {"results": {"bindings": [{"s": {"value": "x"}}]}}

        done = repo.finish_message.await_args
        assert done.kwargs["content"] == "final answer"
        assert done.kwargs["status"] == "complete"
        repo.touch_session.assert_awaited_once()

    async def test_only_last_executed_query_becomes_a_step(self, chat_service):
        service, repo, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT ?a WHERE { ?a ?p ?o } LIMIT 1"}),
            _tool_turn("execute_sparql_query", {"query": "SELECT ?b WHERE { ?b ?p ?o } LIMIT 1"}),
            _answer_turn("done"),
        ]

        await service.process(ChatRequest(message="hi"))

        repo.start_step.assert_awaited_once()
        assert "?b" in repo.start_step.await_args.kwargs["args"]["query"]


class TestProcessResolveEntity:
    async def test_feeds_candidates_back_then_answers(self, chat_service):
        service, _, llm, _, lucene = chat_service
        lucene.search.return_value = [{"uri": "http://x/1", "label": "Rose", "score": 2.0}]
        llm.chat_with_tools.side_effect = [
            _tool_turn("resolve_entity", {"term": "rose"}),
            _answer_turn("Roses found."),
        ]

        resp = await service.process(ChatRequest(message="find rose"))

        lucene.search.assert_awaited_once()
        # No query was executed, so the loop's own answer text is returned directly.
        assert resp.answer == "Roses found."
        llm.generate_answer.assert_not_awaited()


class TestProcessClarification:
    async def test_returns_question_and_ends(self, chat_service):
        service, _, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("ask_clarification", {"question": "Which species?"}),
        ]

        resp = await service.process(ChatRequest(message="vague"))

        assert resp.answer == "Which species?"
        assert resp.llm_generated_query == ""

    async def test_writes_no_step(self, chat_service):
        service, repo, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("ask_clarification", {"question": "Which species?"}),
        ]

        await service.process(ChatRequest(message="vague"))

        repo.start_step.assert_not_awaited()
        assert repo.finish_message.await_args.kwargs["content"] == "Which species?"


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


class TestProcessUsePreviousResults:
    async def test_reuses_prior_turn_results(self, chat_service):
        service, repo, llm, _, _ = chat_service
        step_id = uuid.uuid4()
        # The turn map is keyed on messages.turn, not on the position in the window.
        repo.get_history = AsyncMock(return_value=_history_with_data(7, step_id))
        repo.get_step_result = AsyncMock(
            return_value=("sparql_query", {"results": {"bindings": [{"v": {"value": "1"}}]}})
        )
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 7}),
            _answer_turn("reused"),
        ]

        resp = await service.process(ChatRequest(message="and again"))

        assert resp.llm_generated_query == "SELECT ?old {}"
        assert '"value": "1"' in resp.sparql_query_result
        repo.get_step_result.assert_awaited_once_with(step_id)
        llm.generate_answer.assert_awaited_once()
        # Reused data is not written again as a step of this turn.
        repo.start_step.assert_not_awaited()

    async def test_unknown_turn_falls_back_to_latest(self, chat_service):
        service, repo, llm, _, _ = chat_service
        step_id = uuid.uuid4()
        repo.get_history = AsyncMock(return_value=_history_with_data(7, step_id))
        repo.get_step_result = AsyncMock(
            return_value=("sparql_query", {"results": {"bindings": []}})
        )
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 1}),
            _answer_turn("reused"),
        ]

        await service.process(ChatRequest(message="and again"))

        repo.get_step_result.assert_awaited_once_with(step_id)

    async def test_no_previous_data_returns_fixed_answer(self, chat_service):
        service, repo, llm, _, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 1}),
        ]

        resp = await service.process(ChatRequest(message="and again"))

        assert "no previous query results" in resp.answer
        repo.get_step_result.assert_not_awaited()
        llm.generate_answer.assert_not_awaited()

    async def test_reusable_turns_are_listed_in_the_system_prompt(self, chat_service):
        service, repo, llm, _, _ = chat_service
        repo.get_history = AsyncMock(return_value=_history_with_data(7, uuid.uuid4()))
        llm.chat_with_tools.side_effect = [_answer_turn("ok")]

        await service.process(ChatRequest(message="hi"))

        system_prompt = llm.chat_with_tools.await_args.args[0][0]["content"]
        assert "Turn 7: SELECT ?old {}" in system_prompt


class TestProcessBadQueryRetry:
    async def test_failed_query_is_fed_back_and_retried(self, chat_service):
        service, _, llm, sparql, _ = chat_service
        llm.chat_with_tools.side_effect = [
            _tool_turn("execute_sparql_query", {"query": "SELECT bad"}),
            _tool_turn("execute_sparql_query", {"query": "SELECT ?s WHERE { ?s ?p ?o }"}),
            _answer_turn("recovered"),
        ]
        sparql.execute.side_effect = [
            SparqlQueryException("syntax error"),
            '{"results": {"bindings": []}}',
        ]

        resp = await service.process(ChatRequest(message="hi"))

        assert resp.answer == "final answer"
        assert sparql.execute.await_count == 2


class TestProcessMaxIterations:
    async def test_forces_answer_when_loop_exhausted(self, chat_service):
        service, _, llm, sparql, _ = chat_service
        service.settings.chat_max_tool_iterations = 2
        llm.chat_with_tools.return_value = _tool_turn(
            "execute_sparql_query", {"query": "SELECT ?s WHERE { ?s ?p ?o }"}
        )

        resp = await service.process(ChatRequest(message="hi"))

        assert resp.answer == "final answer"
        assert llm.chat_with_tools.await_count == 2
        llm.generate_answer.assert_awaited_once()


class TestModels:
    async def test_delegates_to_llm(self, chat_service):
        service, _, llm, _, _ = chat_service
        result = await service.models()
        assert result.models == {"m"}
        llm.get_models.assert_awaited_once()


class TestGetFullTable:
    async def test_parses_table(self, chat_service, mocker, sparql_results_json):
        service, _, _, sparql, _ = chat_service
        mocker.patch(
            "src.services.chat_service.load_prompt",
            return_value="SELECT ?name ?count WHERE { ?s ?p ?o }",
        )
        sparql.execute.return_value = sparql_results_json

        resp = await service.get_full_table(limit=None)

        assert resp.full_table.columns == ["name", "count"]
        assert resp.full_table.rows[0] == {"name": "Rose", "count": 5}

    async def test_appends_limit(self, chat_service, mocker, sparql_results_json):
        service, _, _, sparql, _ = chat_service
        mocker.patch(
            "src.services.chat_service.load_prompt",
            return_value="SELECT ?name ?count WHERE { ?s ?p ?o }",
        )
        sparql.execute.return_value = sparql_results_json

        await service.get_full_table(limit=10)

        sent_query = sparql.execute.await_args.args[0]
        assert sent_query.endswith("LIMIT 10")
