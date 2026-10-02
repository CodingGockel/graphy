from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.llm_service import LLMService, LLMTurn
from src.util.exceptions import LLMNoContentException, LLMServiceException
from tests.factories import (
    FakeStream,
    make_chunk,
    make_completion,
    make_message,
    make_models,
    make_tool_call,
    make_tool_call_delta,
)


def _make_service(settings_stub, *, create=None, models_list=None):
    client = MagicMock()
    client.chat.completions.create = create if create is not None else AsyncMock()
    client.models.list = models_list if models_list is not None else AsyncMock()
    return LLMService(client=client, settings=settings_stub), client


async def _loop_call(service) -> tuple[list[str], LLMTurn]:
    """Run one tool-loop call; return its thinking deltas and the turn it ends with."""
    items = [item async for item in service.chat_with_tools(messages=[], tools=[])]
    assert isinstance(items[-1], LLMTurn)
    return items[:-1], items[-1]


async def _turn(service) -> LLMTurn:
    return (await _loop_call(service))[1]


def _streaming(settings_stub, chunks, error=None):
    """A service whose tool loop is streamed, with a stream of the given chunks."""
    settings_stub.llm_stream_tool_loop = True
    stream = FakeStream(chunks, error)
    service, client = _make_service(settings_stub, create=AsyncMock(return_value=stream))
    return service, client, stream


class TestSparqlModelProperty:
    def test_reads_from_settings(self, settings_stub):
        service, _ = _make_service(settings_stub)
        assert service.sparql_model == "test-model"


class TestChatWithTools:
    async def test_structured_tool_call(self, settings_stub):
        tc = make_tool_call("execute_sparql_query", '{"query": "SELECT ?s {}"}')
        completion = make_completion(make_message(tool_calls=[tc]))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await _turn(service)

        assert turn.answer is None
        [call] = turn.tool_calls
        assert call.name == "execute_sparql_query"
        assert call.arguments == {"query": "SELECT ?s {}"}

    async def test_several_tool_calls_are_all_returned(self, settings_stub):
        calls = [
            make_tool_call("resolve_entity", '{"term": "Vienna"}', "call_1"),
            make_tool_call("resolve_entity", '{"term": "Jena"}', "call_2"),
        ]
        completion = make_completion(make_message(tool_calls=calls))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await _turn(service)

        assert [(c.tool_call_id, c.arguments["term"]) for c in turn.tool_calls] == [
            ("call_1", "Vienna"), ("call_2", "Jena"),
        ]

    @pytest.mark.parametrize("arguments", ["", "{}", "null"])
    async def test_tool_call_without_arguments(self, settings_stub, arguments):
        completion = make_completion(make_message(tool_calls=[make_tool_call("finish", arguments)]))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        [call] = (await _turn(service)).tool_calls

        assert (call.name, call.arguments) == ("finish", {})

    async def test_invalid_tool_arguments_raise(self, settings_stub):
        tc = make_tool_call("execute_sparql_query", "not-json")
        completion = make_completion(make_message(tool_calls=[tc]))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))
        with pytest.raises(LLMServiceException):
            await _turn(service)

    async def test_recovers_tool_call_from_text_content(self, settings_stub):
        content = (
            '<invoke name="resolve_entity">'
            '<parameter name="term">rose</parameter></invoke>'
        )
        completion = make_completion(make_message(content=content, tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await _turn(service)

        [call] = turn.tool_calls
        assert call.name == "resolve_entity"
        assert call.arguments == {"term": "rose"}

    async def test_recovers_tool_call_from_json_content(self, settings_stub):
        content = '{"name": "ask_clarification", "arguments": {"question": "which?"}}'
        completion = make_completion(make_message(content=content, tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await _turn(service)

        assert turn.tool_calls[0].name == "ask_clarification"
        assert turn.tool_calls[0].arguments == {"question": "which?"}

    async def test_plain_text_answer(self, settings_stub):
        completion = make_completion(make_message(content="Here is the answer.", tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        turn = await _turn(service)

        assert turn.tool_calls == []
        assert turn.answer == "Here is the answer."

    async def test_tool_choice_comes_from_the_settings(self, settings_stub):
        completion = make_completion(make_message(tool_calls=[make_tool_call("finish", "{}")]))
        for choice in ("auto", "required"):
            settings_stub.llm_tool_choice = choice
            service, client = _make_service(
                settings_stub, create=AsyncMock(return_value=completion)
            )
            await _turn(service)
            assert client.chat.completions.create.await_args.kwargs["tool_choice"] == choice

    async def test_empty_response_raises_no_content(self, settings_stub):
        completion = make_completion(make_message(content=None, tool_calls=None))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))
        with pytest.raises(LLMNoContentException):
            await _turn(service)

    async def test_client_error_raises_service_exception(self, settings_stub):
        service, _ = _make_service(
            settings_stub, create=AsyncMock(side_effect=RuntimeError("api down"))
        )
        with pytest.raises(LLMServiceException):
            await _turn(service)


class TestChatWithToolsNotStreamed:
    """`llm_stream_tool_loop` off (the default of the test settings)."""

    async def test_no_stream_is_requested(self, settings_stub):
        completion = make_completion(make_message(content="Here is the answer."))
        service, client = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        deltas, turn = await _loop_call(service)

        assert deltas == []
        assert turn.answer == "Here is the answer."
        assert "stream" not in client.chat.completions.create.await_args.kwargs

    async def test_reasoning_is_passed_on_in_one_piece(self, settings_stub):
        completion = make_completion(make_message(content="<think>why</think>The answer."))
        service, _ = _make_service(settings_stub, create=AsyncMock(return_value=completion))

        deltas, turn = await _loop_call(service)

        assert deltas == ["why"]
        assert turn.answer == "The answer."

    async def test_required_all_text_next_to_a_tool_call_is_reasoning(self, settings_stub):
        settings_stub.llm_tool_choice = "required"
        # The closing tag is missing in front of a tool call.
        message = make_message(
            content="<think>I need a query.\n\nLet me look it up.",
            tool_calls=[make_tool_call("execute_sparql_query", '{"query": "ASK {}"}')],
        )
        service, _ = _make_service(
            settings_stub, create=AsyncMock(return_value=make_completion(message))
        )

        deltas, turn = await _loop_call(service)

        assert deltas == ["I need a query.\n\nLet me look it up."]
        assert turn.tool_calls[0].arguments == {"query": "ASK {}"}


class TestChatWithToolsStreamed:
    async def test_tool_call_split_over_many_deltas(self, settings_stub):
        service, client, stream = _streaming(
            settings_stub,
            [
                make_chunk(tool_calls=[make_tool_call_delta(0, "call_1", "execute_sparql_query", "")]),
                make_chunk(tool_calls=[make_tool_call_delta(0, arguments='{"query": ')]),
                make_chunk(tool_calls=[make_tool_call_delta(0, arguments='"SELECT ?s {}"}')]),
                make_chunk(finish_reason="tool_calls"),
            ],
        )

        deltas, turn = await _loop_call(service)

        assert deltas == []
        [call] = turn.tool_calls
        assert call.tool_call_id == "call_1"
        assert call.name == "execute_sparql_query"
        assert call.arguments == {"query": "SELECT ?s {}"}
        # the rebuilt message carries the call, for the transcript of the next iteration
        assert turn.raw_message.tool_calls[0].function.arguments == '{"query": "SELECT ?s {}"}'
        assert client.chat.completions.create.await_args.kwargs["stream"] is True
        assert stream.closed

    async def test_two_tool_calls_are_rebuilt_in_their_order(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [
                make_chunk(tool_calls=[make_tool_call_delta(0, "call_1", "resolve_entity", "")]),
                make_chunk(tool_calls=[make_tool_call_delta(1, "call_2", "ask_clarification", "")]),
                make_chunk(tool_calls=[make_tool_call_delta(1, arguments='{"question": "?"}')]),
                make_chunk(tool_calls=[make_tool_call_delta(0, arguments='{"term": "rose"}')]),
            ],
        )

        turn = await _turn(service)

        first, second = turn.tool_calls
        assert (first.name, first.arguments) == ("resolve_entity", {"term": "rose"})
        assert (second.name, second.arguments) == ("ask_clarification", {"question": "?"})
        assert len(turn.raw_message.tool_calls) == 2

    async def test_required_streams_all_text_as_reasoning(self, settings_stub):
        settings_stub.llm_tool_choice = "required"
        service, _, _ = _streaming(
            settings_stub,
            [
                make_chunk(content="<think>Just a greeting.\n"),
                make_chunk(content="\nNo data needed.\n\n<minimax:"),
                make_chunk(content="tool_call>\n"),
                make_chunk(tool_calls=[make_tool_call_delta(0, "call_1", "finish", "{}")]),
                make_chunk(finish_reason="tool_calls"),
            ],
        )

        deltas, turn = await _loop_call(service)

        # no tags, no tool-call marker, nothing held back for an answer
        assert "".join(deltas) == "Just a greeting.\n\nNo data needed.\n\n"
        assert [c.name for c in turn.tool_calls] == ["finish"]

    async def test_text_encoded_tool_call_is_recovered_from_the_buffer(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [
                make_chunk(content='<invoke name="resolve_'),
                make_chunk(content='entity"><parameter name="term">rose</para'),
                make_chunk(content="meter></invoke>"),
            ],
        )

        deltas, turn = await _loop_call(service)

        # Nothing but reasoning is passed on live.
        assert deltas == []
        assert turn.tool_calls[0].name == "resolve_entity"
        assert turn.tool_calls[0].arguments == {"term": "rose"}

    async def test_thinking_is_passed_on_while_the_tool_call_is_still_detected(
        self, settings_stub
    ):
        service, _, _ = _streaming(
            settings_stub,
            [
                make_chunk(content="<thi"),
                make_chunk(content="nk>I need "),
                make_chunk(content="a query.</think>"),
                make_chunk(tool_calls=[make_tool_call_delta(0, "call_1", "execute_sparql_query")]),
                make_chunk(tool_calls=[make_tool_call_delta(0, arguments='{"query": "ASK {}"}')]),
            ],
        )

        deltas, turn = await _loop_call(service)

        assert deltas == ["I need ", "a query."]
        assert turn.tool_calls[0].arguments == {"query": "ASK {}"}

    async def test_plain_answer_is_buffered_and_its_reasoning_split_off(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [make_chunk(content="<think>easy</think>Hel"), make_chunk(content="lo.")],
        )

        deltas, turn = await _loop_call(service)

        assert deltas == ["easy"]
        assert turn.tool_calls == []
        assert turn.answer == "Hello."

    async def test_reasoning_content_field_is_thinking(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [make_chunk(reasoning_content="hm"), make_chunk(content="Hello.")],
        )

        deltas, turn = await _loop_call(service)

        assert deltas == ["hm"]
        assert turn.answer == "Hello."

    async def test_reasoning_before_a_lone_closing_tag_is_sent_at_the_end(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [make_chunk(content="why"), make_chunk(content="</think>Hello.")],
        )

        deltas, turn = await _loop_call(service)

        assert deltas == ["why"]
        assert turn.answer == "Hello."

    async def test_answer_after_a_dropped_closing_tag_is_found(self, settings_stub):
        # Blablador drops </think> when a request with tools is streamed.
        service, _, _ = _streaming(
            settings_stub,
            [
                make_chunk(content="<think>Just a greeting.\n"),
                make_chunk(content="\n\nHello!\n\nHow can I help?"),
                make_chunk(finish_reason="stop"),
            ],
        )

        turn = await _turn(service)

        assert turn.answer == "Hello!\n\nHow can I help?"

    async def test_unclosed_block_without_a_gap_is_the_answer(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub, [make_chunk(content="<think>Hello!"), make_chunk(finish_reason="stop")]
        )
        assert (await _turn(service)).answer == "Hello!"

    async def test_reasoning_cut_off_by_the_token_cap_is_no_answer(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [make_chunk(content="<think>Let me\n\n\nthink"), make_chunk(finish_reason="length")],
        )
        with pytest.raises(LLMNoContentException):
            await _turn(service)

    async def test_chunks_without_a_choice_are_skipped(self, settings_stub):
        usage_only = make_chunk()
        usage_only.choices = []
        service, _, _ = _streaming(settings_stub, [usage_only, make_chunk(content="Hello.")])

        assert (await _turn(service)).answer == "Hello."

    async def test_empty_stream_raises_no_content(self, settings_stub):
        service, _, _ = _streaming(settings_stub, [make_chunk(finish_reason="length")])
        with pytest.raises(LLMNoContentException):
            await _turn(service)

    async def test_invalid_tool_arguments_raise(self, settings_stub):
        service, _, _ = _streaming(
            settings_stub,
            [make_chunk(tool_calls=[make_tool_call_delta(0, "call_1", "resolve_entity", "not-json")])],
        )
        with pytest.raises(LLMServiceException):
            await _turn(service)

    async def test_error_in_the_middle_of_the_stream_raises_service_exception(self, settings_stub):
        service, _, stream = _streaming(
            settings_stub, [make_chunk(content="Hel")], error=RuntimeError("connection lost")
        )
        with pytest.raises(LLMServiceException):
            await _turn(service)
        assert stream.closed


class TestGenerateAnswerStream:
    async def _answer(self, settings_stub, mocker, chunks, error=None):
        mocker.patch("src.services.llm_service.load_prompt", return_value="ANSWER PROMPT")
        stream = FakeStream(chunks, error)
        service, client = _make_service(settings_stub, create=AsyncMock(return_value=stream))
        parts = [
            p
            async for p in service.generate_answer_stream(
                "q?", "SPARQL query 1:\nSELECT ?s {}", [{"role": "user", "content": "earlier"}]
            )
        ]
        return parts, client

    async def test_answer_is_streamed_with_its_reasoning_split_off(self, settings_stub, mocker):
        parts, client = await self._answer(
            settings_stub,
            mocker,
            [
                make_chunk(content="<think>one row</thi"),
                make_chunk(content="nk>The "),
                make_chunk(content="answer."),
            ],
        )

        assert parts == [("thinking", "one row"), ("answer", "The "), ("answer", "answer.")]
        kwargs = client.chat.completions.create.await_args.kwargs
        assert kwargs["stream"] is True
        assert "tools" not in kwargs
        # system prompt, the chat so far, then the question with the turn's data
        assert kwargs["messages"] == [
            {"role": "system", "content": "ANSWER PROMPT"},
            {"role": "user", "content": "earlier"},
            {"role": "user", "content": "User question: q?\n\nSPARQL query 1:\nSELECT ?s {}"},
        ]

    async def test_reasoning_content_field_is_thinking(self, settings_stub, mocker):
        parts, _ = await self._answer(
            settings_stub,
            mocker,
            [make_chunk(reasoning_content="one row"), make_chunk(content="The answer.")],
        )
        assert parts == [("thinking", "one row"), ("answer", "The answer.")]

    @pytest.mark.parametrize(
        "chunks",
        [[], [make_chunk(finish_reason="stop")], [make_chunk(content="<think>cut off")]],
    )
    async def test_stream_without_an_answer_raises_no_content(self, settings_stub, mocker, chunks):
        with pytest.raises(LLMNoContentException):
            await self._answer(settings_stub, mocker, chunks)

    async def test_client_error_raises(self, settings_stub, mocker):
        mocker.patch("src.services.llm_service.load_prompt", return_value="ANSWER PROMPT")
        service, _ = _make_service(
            settings_stub, create=AsyncMock(side_effect=RuntimeError("api down"))
        )
        with pytest.raises(LLMServiceException):
            [p async for p in service.generate_answer_stream("q?", "(no query executed)")]

    async def test_error_in_the_middle_of_the_stream_raises(self, settings_stub, mocker):
        with pytest.raises(LLMServiceException):
            await self._answer(
                settings_stub, mocker, [make_chunk(content="The ")], error=RuntimeError("lost")
            )


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
