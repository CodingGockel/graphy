import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, NOT_GIVEN
from openai.types.chat import ChatCompletion, ChatCompletionMessage

from src.util.config import Settings
from src.util.exceptions import LLMNoContentException, LLMServiceException
from src.util.llm_utils import load_prompt
from src.util.sparql_utils import strip_think
from src.models.schemas import ServiceHealth, ModelResponse
from src.util.logger import logger


@dataclass
class ToolCallResult:
    tool_call_id: str
    name: str
    arguments: dict
    raw_message: ChatCompletionMessage


@dataclass
class LLMTurn:
    """One step of the agentic loop: either a tool call to execute, or a
    final natural-language answer (when the model is done calling tools)."""
    tool_call: ToolCallResult | None
    answer: str | None
    raw_message: ChatCompletionMessage


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

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMTurn:
        """Run one agentic turn. Returns either a tool call to execute or, when
        the model produces plain text instead of a tool call, a final answer."""
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model=self.sparql_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens if self.max_tokens is not None else NOT_GIVEN,  # type: ignore
                messages=messages,  # type: ignore
                tools=tools,  # type: ignore
                tool_choice="auto",
            )
        except Exception as e:
            raise LLMServiceException(message=str(e)) from e

        choice = response.choices[0]
        msg = choice.message

        if msg.tool_calls:
            tool_call = msg.tool_calls[0]
            try:
                arguments = json.loads(tool_call.function.arguments)  # type: ignore[union-attr]
            except json.JSONDecodeError as e:
                raise LLMServiceException(
                    message=f"Invalid tool call arguments: {tool_call.function.arguments}"  # type: ignore[union-attr]
                ) from e
            return LLMTurn(
                tool_call=ToolCallResult(
                    tool_call_id=tool_call.id,
                    name=tool_call.function.name,  # type: ignore[union-attr]
                    arguments=arguments,
                    raw_message=msg,
                ),
                answer=None,
                raw_message=msg,
            )

        # 2. Some models (e.g. MiniMax via vLLM) emit the tool call as text in
        #    `content` instead of a parsed tool_calls entry. Try to recover it.
        recovered = self._recover_tool_call_from_content(msg.content)
        if recovered is not None:
            logger.info("Recovered tool call from content: %s", recovered.name)
            return LLMTurn(tool_call=recovered, answer=None, raw_message=msg)

        # 3. No tool call at all → the model is done, this is the final answer.
        if msg.content:
            return LLMTurn(tool_call=None, answer=msg.content, raw_message=msg)

        logger.warning(
            "chat_with_tools: empty response. finish_reason=%s, message=%s",
            choice.finish_reason,
            msg.model_dump_json(),
        )
        raise LLMNoContentException(
            f"LLM returned neither tool calls nor content "
            f"(finish_reason={choice.finish_reason})"
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

    async def generate_answer(
        self,
        user_question: str,
        sparql_query: str,
        sparql_results: str | None,
    ) -> str:
        """Dedicated final-answer call. Uses the static answer-interpreter prompt
        (not the schema-heavy query prompt) and is given only the user question,
        the executed query and its results — no tools available."""
        user_content = (
            f"User question: {user_question}\n\n"
            f"SPARQL query:\n{sparql_query or '(no query executed)'}\n\n"
            f"Query result:\n{sparql_results or '(no results available)'}"
        )
        messages = [
            {"role": "system", "content": self.answer_system_prompt()},
            {"role": "user", "content": user_content},
        ]
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model=self.sparql_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens if self.max_tokens is not None else NOT_GIVEN,  # type: ignore
                messages=messages,  # type: ignore
            )
        except Exception as e:
            raise LLMServiceException(message=str(e)) from e

        content = response.choices[0].message.content
        if content is None:
            raise LLMNoContentException("LLM did not generate a final answer")
        # Strip any <think>…</think> reasoning the model leaked before the answer.
        return strip_think(content)

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
