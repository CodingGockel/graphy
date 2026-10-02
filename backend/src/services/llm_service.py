import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, NOT_GIVEN
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion_message_tool_call import Function

from src.util.config import Settings
from src.util.exceptions import LLMNoContentException, LLMServiceException
from src.util.llm_utils import load_prompt
from src.util.sparql_utils import strip_think
from src.util.think_splitter import (
    OPEN,
    Kind,
    ReasoningOnlySplitter,
    ThinkSplitter,
    reasoning_only,
    split_think,
)
from src.models.schemas import ServiceHealth, ModelResponse
from src.util.logger import logger


# Output-token cap of the title call. Far more than a title needs: a reasoning model
# spends tokens on its <think> block first.
TITLE_MAX_TOKENS = 1024
TITLE_MAX_LENGTH = 80


@dataclass
class ToolCallResult:
    tool_call_id: str
    name: str
    arguments: dict
    raw_message: ChatCompletionMessage


@dataclass
class LLMTurn:
    """One step of the agentic loop: either the tool calls to execute (a model may
    ask for several in one message), or a final natural-language answer (when the
    model wrote text instead of calling a tool). The answer is the model's text
    without its reasoning."""
    tool_calls: list[ToolCallResult]
    answer: str | None
    raw_message: ChatCompletionMessage


def _reasoning(part: Any) -> str:
    """Reasoning that a server sends in a field of its own (next to `content`) instead
    of inside `<think>` tags. Works for a message and for a stream delta."""
    for name in ("reasoning_content", "reasoning"):
        value = getattr(part, name, None)
        if isinstance(value, str) and value:
            return value
    return ""


def _answer_in_unclosed_think(content: str) -> str:
    """The answer inside a `<think>` block that never ends.

    Some servers drop the closing `</think>` when a request with tools is streamed
    (seen with Blablador / MiniMax): reasoning and answer then arrive as one block.
    The tag leaves a gap of blank lines behind; what follows it is the answer.
    Without such a gap the whole block is, so the user gets the text in any case."""
    start = content.rfind(OPEN)
    if start == -1:
        return ""
    block = content[start + len(OPEN):]
    _, gap, rest = block.partition("\n\n\n")
    return (rest if gap and rest.strip() else block).strip()


class LLMService:
    def __init__(
        self,
        client: AsyncOpenAI,
        settings: Settings,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ):
        self.client = client
        self.settings = settings
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    def sparql_model(self) -> str:
        return self.settings.blablador_sparql_model

    def query_system_prompt(self) -> str:
        """System prompt for the SPARQL query-generation tool loop (schema-driven)."""
        return load_prompt(self.settings.system_prompt_path)

    def answer_system_prompt(self) -> str:
        """Static, KG-agnostic system prompt for the dedicated final answer call."""
        return load_prompt(self.settings.answer_system_prompt_path)

    def _max_tokens(self) -> Any:
        return self.max_tokens if self.max_tokens is not None else NOT_GIVEN

    async def _stream(self, **request: Any) -> AsyncIterator[ChatCompletionChunk]:
        """The chunks of a streamed completion that carry a choice. Errors, also in the
        middle of the stream, become an LLMServiceException."""
        try:
            stream: Any = await self.client.chat.completions.create(stream=True, **request)  # type: ignore
            try:
                async for chunk in stream:
                    if chunk.choices:
                        yield chunk
            finally:
                # Also when the consumer stops early (cancelled turn): release the connection.
                await stream.close()
        except Exception as e:
            raise LLMServiceException(message=str(e)) from e

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[str | LLMTurn]:
        """Run one agentic turn. Yields the model's reasoning as it arrives (strings)
        and, as the last item, the `LLMTurn`: the tool calls to execute or, when the
        model produced plain text instead, a final answer.

        Stream for display, parse on the buffer: only reasoning is passed on live.
        Everything else is collected, because it may be a text-encoded tool call or the
        final answer, and the tool detection runs on the complete message.

        With `llm_tool_choice` = `required` the model has to answer with a tool call,
        so all of its text is reasoning (servers tend to drop the closing `</think>`
        in front of a tool call, which makes the tags useless for telling them apart).
        """
        required = self.settings.llm_tool_choice == "required"
        request: dict[str, Any] = dict(
            model=self.sparql_model,
            temperature=self.temperature,
            max_tokens=self._max_tokens(),
            messages=messages,
            tools=tools,
            tool_choice=self.settings.llm_tool_choice,
        )

        if not self.settings.llm_stream_tool_loop:
            try:
                response: ChatCompletion = await self.client.chat.completions.create(**request)  # type: ignore
            except Exception as e:
                raise LLMServiceException(message=str(e)) from e
            choice = response.choices[0]
            # Not streamed, but still shown: the reasoning as one piece.
            text = choice.message.content or ""
            thinking = "\n\n".join(
                part
                for part in (
                    _reasoning(choice.message),
                    reasoning_only(text) if required else split_think(text)[0],
                )
                if part
            )
            if thinking:
                yield thinking
            yield self._turn_from_message(choice.message, choice.finish_reason)
            return

        splitter = ReasoningOnlySplitter() if required else ThinkSplitter()
        content = ""
        streamed_thinking = False
        calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None

        async for chunk in self._stream(**request):
            choice = chunk.choices[0]
            delta = choice.delta
            finish_reason = choice.finish_reason or finish_reason
            reasoning = _reasoning(delta)
            if reasoning:
                yield reasoning
            if delta.content:
                content += delta.content
                for kind, text in splitter.feed(delta.content):
                    if kind == "thinking":
                        streamed_thinking = True
                        yield text
            # A tool call arrives in fragments: id and name first, then the arguments.
            for fragment in delta.tool_calls or []:
                call = calls.setdefault(fragment.index, {"id": "", "name": "", "arguments": ""})
                if fragment.id:
                    call["id"] = fragment.id
                if fragment.function is not None:
                    call["name"] += fragment.function.name or ""
                    call["arguments"] += fragment.function.arguments or ""
        for kind, text in splitter.flush():
            if kind == "thinking":
                streamed_thinking = True
                yield text

        # Reasoning that only ended with a lone </think> was not recognized on the way.
        if not streamed_thinking and not required:
            late_thinking = split_think(content)[0]
            if late_thinking:
                yield late_thinking

        message = ChatCompletionMessage(
            role="assistant",
            content=content or None,
            tool_calls=[
                ChatCompletionMessageToolCall(
                    id=call["id"],
                    type="function",
                    function=Function(name=call["name"], arguments=call["arguments"]),
                )
                for _, call in sorted(calls.items())
            ]
            or None,
        )
        yield self._turn_from_message(message, finish_reason)

    def _turn_from_message(
        self, msg: ChatCompletionMessage, finish_reason: str | None
    ) -> LLMTurn:
        """What a complete assistant message of the loop means: tool calls (structured,
        or one recovered from text) or the final answer."""
        if msg.tool_calls:
            tool_calls: list[ToolCallResult] = []
            for tool_call in msg.tool_calls:
                raw_arguments = tool_call.function.arguments  # type: ignore[union-attr]
                try:
                    # A tool without parameters may come with no arguments at all.
                    arguments = json.loads(raw_arguments or "{}")
                except json.JSONDecodeError as e:
                    raise LLMServiceException(
                        message=f"Invalid tool call arguments: {raw_arguments}"
                    ) from e
                tool_calls.append(
                    ToolCallResult(
                        tool_call_id=tool_call.id,
                        name=tool_call.function.name,  # type: ignore[union-attr]
                        arguments=arguments if isinstance(arguments, dict) else {},
                        raw_message=msg,
                    )
                )
            return LLMTurn(tool_calls=tool_calls, answer=None, raw_message=msg)

        # 2. Some models (e.g. MiniMax via vLLM) emit the tool call as text in
        #    `content` instead of a parsed tool_calls entry. Try to recover it.
        recovered = self._recover_tool_call_from_content(msg.content)
        if recovered is not None:
            logger.info("Recovered tool call from content: %s", recovered.name)
            return LLMTurn(tool_calls=[recovered], answer=None, raw_message=msg)

        # 3. No tool call at all → the model is done, this is the final answer.
        answer = split_think(msg.content or "")[1]
        if not answer and finish_reason != "length":
            # Not for output cut off by the token cap: that really is reasoning only.
            answer = _answer_in_unclosed_think(msg.content or "")
        if answer:
            return LLMTurn(tool_calls=[], answer=answer, raw_message=msg)

        logger.warning(
            "chat_with_tools: empty response. finish_reason=%s, message=%s",
            finish_reason,
            msg.model_dump_json(),
        )
        raise LLMNoContentException(
            f"LLM returned neither tool calls nor content "
            f"(finish_reason={finish_reason})"
        )

    def _recover_tool_call_from_content(
        self, content: str | None
    ) -> "ToolCallResult | None":
        """
        Best-effort recovery of a tool call that the backend placed in the
        message content as raw text instead of a parsed tool_calls entry.

        Handles:
          - MiniMax/Anthropic XML: <invoke name="X"><parameter name="p">v</parameter></invoke>
          - bare JSON: {"name": "...", "arguments": {...}}
          - "parameters" instead of "arguments"
          - markdown ```json ... ``` fences
          - Hermes-style <tool_call>...</tool_call> wrappers
        """
        if not content:
            return None

        text = content.strip()

        # Strip <think>...</think> reasoning blocks.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # MiniMax/Anthropic XML format:
        #   <invoke name="execute_sparql_query">
        #     <parameter name="query">SELECT ...</parameter>
        #   </invoke>
        # Non-greedy capture is safe because SPARQL uses <...> URIs, not </invoke>.
        invoke = re.search(r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', text, re.DOTALL)
        if invoke:
            name = invoke.group(1)
            args: dict[str, Any] = {}
            for pm in re.finditer(
                r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>',
                invoke.group(2),
                re.DOTALL,
            ):
                args[pm.group(1)] = pm.group(2).strip()
            return ToolCallResult(
                tool_call_id="",
                name=name,
                arguments=args,
                raw_message=ChatCompletionMessage(role="assistant", content=content),
            )

        wrapped = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
        if wrapped:
            text = wrapped.group(1).strip()

        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        brace = text.find("{")
        if brace == -1:
            return None
        text = text[brace:]

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        name = data.get("name")
        arguments = data.get("arguments")
        if arguments is None:
            arguments = data.get("parameters")
        if arguments is None:
            arguments = {}

        # Arguments may itself be a JSON string.
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        if not isinstance(name, str) or not isinstance(arguments, dict):
            return None

        return ToolCallResult(
            tool_call_id="",
            name=name,
            arguments=arguments,
            raw_message=ChatCompletionMessage(role="assistant", content=content),
        )

    async def generate_answer_stream(
        self,
        user_question: str,
        data: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[tuple[Kind, str]]:
        """Dedicated final-answer call, streamed as `(kind, delta)` with the kind
        `thinking` or `answer`. Uses the static answer-interpreter prompt (not the
        schema-heavy query prompt) and is given the earlier questions and answers of
        the chat, the user question and `data`: everything the turn's steps found
        (resolved entities, every query with its result) — no tools available."""
        messages = [
            {"role": "system", "content": self.answer_system_prompt()},
            *(history or []),
            {"role": "user", "content": f"User question: {user_question}\n\n{data}"},
        ]
        splitter = ThinkSplitter()
        answered = False
        async for chunk in self._stream(
            model=self.sparql_model,
            temperature=self.temperature,
            max_tokens=self._max_tokens(),
            messages=messages,
        ):
            delta = chunk.choices[0].delta
            reasoning = _reasoning(delta)
            if reasoning:
                yield "thinking", reasoning
            if delta.content:
                for part in splitter.feed(delta.content):
                    answered = answered or part[0] == "answer"
                    yield part
        for part in splitter.flush():
            answered = answered or part[0] == "answer"
            yield part

        if not answered:
            raise LLMNoContentException("LLM did not generate a final answer")

    async def generate_title(self, question: str) -> str:
        """A short session title for the first question of a session, as one line."""
        messages = [
            {"role": "system", "content": load_prompt(self.settings.session_title_prompt_path)},
            {"role": "user", "content": question},
        ]
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model=self.sparql_model,
                temperature=self.temperature,
                max_tokens=TITLE_MAX_TOKENS,
                messages=messages,  # type: ignore
            )
        except Exception as e:
            raise LLMServiceException(message=str(e)) from e

        choice = response.choices[0]
        text = strip_think(choice.message.content or "")
        # Reasoning that was cut off by the token cap is not a title.
        lines = [] if "<think>" in text else [line.strip() for line in text.splitlines()]
        title = next((line for line in lines if line), "")
        title = " ".join(title.strip("\"'`*#“”„«» ").split()).rstrip(".")
        if not title:
            raise LLMNoContentException(
                f"LLM did not generate a title (finish_reason={choice.finish_reason})"
            )
        return title[:TITLE_MAX_LENGTH].rstrip()

    async def get_models(self) -> ModelResponse:
        try:
            models = await asyncio.wait_for(self.client.models.list(), timeout=5.0)
        except Exception as e:
            raise LLMServiceException(message=str(e)) from e
        return ModelResponse(models={m.id for m in models.data})

    async def health_check(self) -> ServiceHealth:
        timeout = 5.0
        try:
            models = await asyncio.wait_for(self.client.models.list(), timeout=timeout)
            available = {m.id for m in models.data}
            required = {self.sparql_model}
            missing = required - available
            if missing:
                return ServiceHealth(
                    status="degraded",
                    error=f"invalid models: {sorted(missing)}",
                    additional_attributes={
                        "checked_models": sorted(required),
                        "invalid_models": sorted(missing),
                    },
                )
            return ServiceHealth(
                status="ok",
                additional_attributes={"checked_models": sorted(required)},
            )
        except asyncio.TimeoutError:
            return ServiceHealth(status="down", error=f"timeout after {timeout}s")
        except Exception as e:
            return ServiceHealth(status="down", error=str(e))
