import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai.types.chat import ChatCompletionMessage

from src.models.schemas import ChatRequest, ModelResponse
from src.services.chat_service import ChatService
from src.services.llm_service import LLMTurn, ToolCallResult
from src.util.exceptions import SparqlQueryException
from tests.factories import make_db_message


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
    repo.save_message = AsyncMock()
    mocker.patch("src.services.chat_service.ChatRepository", return_value=repo)

    llm = MagicMock()
    llm._query_system_prompt = MagicMock(return_value="SYSTEM PROMPT")
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
        # user message + assistant message persisted
        assert repo.save_message.await_count == 2


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


class TestProcessUsePreviousResults:
    async def test_reuses_prior_turn_results(self, chat_service):
        service, repo, llm, _, _ = chat_service
        repo.get_history = AsyncMock(
            return_value=[
                make_db_message("user", "earlier question"),
                make_db_message(
                    "assistant",
                    "earlier answer",
                    sparql_query="SELECT ?old {}",
                    sparql_results='{"results": {"bindings": [{"v": {"value": "1"}}]}}',
                ),
            ]
        )
        llm.chat_with_tools.side_effect = [
            _tool_turn("use_previous_results", {"reference_turn": 1}),
            _answer_turn("reused"),
        ]

        resp = await service.process(ChatRequest(message="and again"))

        assert resp.llm_generated_query == "SELECT ?old {}"
        llm.generate_answer.assert_awaited_once()


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
