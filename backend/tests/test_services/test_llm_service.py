from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.llm_service import LLMService
from src.util.exceptions import LLMNoContentException, LLMServiceException
from tests.factories import make_completion, make_message, make_models, make_tool_call


def _make_service(settings_stub, *, create=None, models_list=None):
    client = MagicMock()
    client.chat.completions.create = create if create is not None else AsyncMock()
    client.models.list = models_list if models_list is not None else AsyncMock()
    return LLMService(client=client, settings=settings_stub), client


class TestSparqlModelProperty:
    def test_reads_from_settings(self, settings_stub):
        service, _ = _make_service(settings_stub)
        assert service.sparql_model == "test-model"


class TestChatWithTools:
    async def test_structured_tool_call(self, settings_stub):
        tc = make_tool_call("execute_sparql_query", '{"query": "SELECT ?s {}"}')
        completion = make_completion(make_message(tool_calls=[tc]))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await service.chat_with_tools(messages=[], tools=[])

        assert turn.answer is None
        assert turn.tool_call is not None
        assert turn.tool_call.name == "execute_sparql_query"
        assert turn.tool_call.arguments == {"query": "SELECT ?s {}"}

    async def test_invalid_tool_arguments_raise(self, settings_stub):
        tc = make_tool_call("execute_sparql_query", "not-json")
        completion = make_completion(make_message(tool_calls=[tc]))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))
        with pytest.raises(LLMServiceException):
            await service.chat_with_tools(messages=[], tools=[])

    async def test_recovers_tool_call_from_text_content(self, settings_stub):
        content = (
            '<invoke name="resolve_entity">'
            '<parameter name="term">rose</parameter></invoke>'
        )
        completion = make_completion(make_message(content=content, tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await service.chat_with_tools(messages=[], tools=[])

        assert turn.tool_call is not None
        assert turn.tool_call.name == "resolve_entity"
        assert turn.tool_call.arguments == {"term": "rose"}

    async def test_recovers_tool_call_from_json_content(self, settings_stub):
        content = '{"name": "ask_clarification", "arguments": {"question": "which?"}}'
        completion = make_completion(make_message(content=content, tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await service.chat_with_tools(messages=[], tools=[])

        assert turn.tool_call.name == "ask_clarification"
        assert turn.tool_call.arguments == {"question": "which?"}

    async def test_plain_text_answer(self, settings_stub):
        completion = make_completion(make_message(content="Here is the answer.", tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await service.chat_with_tools(messages=[], tools=[])

        assert turn.tool_call is None
        assert turn.answer == "Here is the answer."

    async def test_empty_response_raises_no_content(self, settings_stub):
        completion = make_completion(make_message(content=None, tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))
        with pytest.raises(LLMNoContentException):
            await service.chat_with_tools(messages=[], tools=[])

    async def test_client_error_raises_service_exception(self, settings_stub):
        service, _ = _make_service(
            settings_stub, create=AsyncMock(side_effect=RuntimeError("api down"))
        )
        with pytest.raises(LLMServiceException):
            await service.chat_with_tools(messages=[], tools=[])


class TestGenerateAnswer:
    async def test_returns_content_with_think_stripped(self, settings_stub, mocker):
        mocker.patch("src.services.llm_service.load_prompt", return_value="ANSWER PROMPT")
        completion = make_completion(make_message(content="<think>reasoning</think>The answer."))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        answer = await service.generate_answer("q?", "SELECT ?s {}", "{}")

        assert answer == "The answer."

    async def test_no_content_raises(self, settings_stub, mocker):
        mocker.patch("src.services.llm_service.load_prompt", return_value="ANSWER PROMPT")
        completion = make_completion(make_message(content=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))
        with pytest.raises(LLMNoContentException):
            await service.generate_answer("q?", "SELECT ?s {}", None)

    async def test_client_error_raises(self, settings_stub, mocker):
        mocker.patch("src.services.llm_service.load_prompt", return_value="ANSWER PROMPT")
        service, _ = _make_service(
            settings_stub, create=AsyncMock(side_effect=RuntimeError("api down"))
        )
        with pytest.raises(LLMServiceException):
            await service.generate_answer("q?", "SELECT ?s {}", None)


class TestGenerateTitle:
    async def _title(self, settings_stub, mocker, content):
        mocker.patch("src.services.llm_service.load_prompt", return_value="TITLE PROMPT")
        completion = make_completion(make_message(content=content))
        service, client = _make_service(settings_stub, create=AsyncMock(return_value=completion))
        return await service.generate_title("When do tulips flower?"), client

    async def test_sends_the_question_with_a_token_cap(self, settings_stub, mocker):
        title, client = await self._title(settings_stub, mocker, "Tulip flowering")

        assert title == "Tulip flowering"
        kwargs = client.chat.completions.create.await_args.kwargs
        assert kwargs["messages"] == [
            {"role": "system", "content": "TITLE PROMPT"},
            {"role": "user", "content": "When do tulips flower?"},
        ]
        assert isinstance(kwargs["max_tokens"], int)

    async def test_think_block_quotes_and_extra_lines_are_removed(self, settings_stub, mocker):
        content = '<think>a title…</think>\n\n"Tulip   flowering."\nSecond line'
        title, _ = await self._title(settings_stub, mocker, content)
        assert title == "Tulip flowering"

    async def test_long_title_is_cut(self, settings_stub, mocker):
        title, _ = await self._title(settings_stub, mocker, "word " * 100)
        assert len(title) <= 80

    @pytest.mark.parametrize("content", [None, "", "  \n ", "<think>cut off by the cap"])
    async def test_no_usable_title_raises(self, settings_stub, mocker, content):
        with pytest.raises(LLMNoContentException):
            await self._title(settings_stub, mocker, content)

    async def test_client_error_raises(self, settings_stub, mocker):
        mocker.patch("src.services.llm_service.load_prompt", return_value="TITLE PROMPT")
        service, _ = _make_service(
            settings_stub, create=AsyncMock(side_effect=RuntimeError("api down"))
        )
        with pytest.raises(LLMServiceException):
            await service.generate_title("q?")


class TestGetModels:
    async def test_returns_model_ids(self, settings_stub):
        service, _ = _make_service(
            settings_stub, models_list=AsyncMock(return_value=make_models("a", "b"))
        )
        result = await service.get_models()
        assert result.models == {"a", "b"}


class TestHealthCheck:
    async def test_ok_when_configured_model_present(self, settings_stub):
        service, _ = _make_service(
            settings_stub, models_list=AsyncMock(return_value=make_models("test-model", "other"))
        )
        health = await service.health_check()
        assert health.status == "ok"

    async def test_degraded_when_model_missing(self, settings_stub):
        service, _ = _make_service(
            settings_stub, models_list=AsyncMock(return_value=make_models("other"))
        )
        health = await service.health_check()
        assert health.status == "degraded"
        assert "invalid models" in health.error

    async def test_down_on_exception(self, settings_stub):
        service, _ = _make_service(
            settings_stub, models_list=AsyncMock(side_effect=RuntimeError("unreachable"))
        )
        health = await service.health_check()
        assert health.status == "down"
        assert "unreachable" in health.error
