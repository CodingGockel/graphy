import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.models.events import (
    AnswerEvent,
    ChatEvent,
    DoneEvent,
    SessionEvent,
    SessionTitleEvent,
    StepFinishedEvent,
    StepKind,
    StepStartedEvent,
    ThinkingEvent,
)
from src.models.schemas import ModelResponse, FullTable, FullTableResponse
from src.util.sparql_utils import (
    count_rows,
    ensure_limit,
    parse_sparql_bindings,
    results_to_json,
    results_to_text,
    strip_think,
)
from src.db.models import Message
from src.db.repository import ChatRepository, reusable_data
from src.services.llm_service import LLMService, LLMTurn, ToolCallResult
from src.services.sparql_service import SparqlService
from src.services.lucene_service import LuceneService
from src.util.exceptions import AppException, SessionNotFoundException, SparqlQueryException
from src.util.config import Settings
from src.util.logger import logger
from src.util.llm_utils import load_tools, load_prompt
from src.util.think_splitter import split_think

TOOLS: list[dict[str, Any]] = load_tools()

@dataclass
class TurnData:
    """Reusable data of an earlier turn: the query step holding its result. The result
    itself is only loaded (by step id) when use_previous_results asks for it."""
    step_id: uuid.UUID
    query: str


def _build_history(
    messages: list[Message],
) -> tuple[list[dict[str, str]], dict[int, TurnData]]:
    """Convert DB messages into LLM message dicts and a turn->TurnData map for data
    reuse, keyed on `messages.turn` (stable even once the history depth is exceeded)."""
    llm_messages: list[dict[str, str]] = []
    turn_map: dict[int, TurnData] = {}

    for msg in messages:
        if msg.role == "user":
            llm_messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            # An answer written without tools is stored with its <think> block
            # (the frontend shows it); the model must not get it back as history.
            llm_messages.append({"role": "assistant", "content": strip_think(msg.content)})
            data = reusable_data(msg)
            if data is not None:
                turn_map[msg.turn] = TurnData(step_id=data[0], query=data[1])

    return llm_messages, turn_map


@dataclass
class TurnState:
    """What a run has produced so far. Owned by the caller of ChatService.run(), which
    keeps it up to date, so the caller can still store a turn that was cut off."""
    message_id: uuid.UUID | None = None
    answer: str = ""
    # The reasoning that belongs to the message: what was written since the last
    # step (a step takes the reasoning before it along). Stays empty when reasoning
    # is not stored (`persist_thinking`).
    thinking: str = ""


@dataclass
class StepOutcome:
    """Result of one executed tool call."""
    ok: bool
    # Rows (sparql_query, previous_results) or candidates (resolve_entity).
    count: int | None = None
    # Stored in steps.result; never sent in an event.
    result: Any = None
    error: str | None = None
    # Fed back to the model as the tool result.
    output: str = ""
    # Set by a step that provides the data for the final answer.
    query: str | None = None
    results: str | None = None
    # Set by a step that ends the loop with a fixed answer.
    final_answer: str | None = None


def _truncate_results(raw: str, max_rows: int = 30) -> str:
    """Shrink a SPARQL JSON result before re-injecting it into the tool loop: keep the
    first `max_rows` bindings and note the true total. The loop only needs a representative
    sample to decide its next step; the *full* result still goes to the final-answer call
    (last_results), so nothing is lost. Prevents the monotonic context growth that caused
    413s / max-iteration spirals on large result sets."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    bindings = data.get("results", {}).get("bindings")
    if not isinstance(bindings, list) or len(bindings) <= max_rows:
        return raw
    total = len(bindings)
    data["results"]["bindings"] = bindings[:max_rows]
    return (
        json.dumps(data)
        + f"\n\n[Truncated for the tool loop: showing {max_rows} of {total} rows. "
        "The full result set is used to write the final answer.]"
    )


def _format_candidates(term: str, candidates: list[dict]) -> str:
    """Render resolve_entity results as a tool message the model can act on."""
    if not candidates:
        return (
            f"No candidates found for '{term}'. Try a different spelling or the "
            "scientific name, or fall back to a SPARQL query using "
            'FILTER(CONTAINS(LCASE(?label), "...")) on rdfs:label.'
        )
    lines = [f"Candidates for '{term}' (use the URI directly in your SPARQL query):"]
    for c in candidates:
        lines.append(f"- <{c['uri']}> — \"{c['label']}\" (score {c['score']:.2f})")
    return "\n".join(lines)


def _available_data_note(turn_map: dict[int, TurnData]) -> str:
    if not turn_map:
        return ""
    lines = [
        "\n\n# Reusable Data from Previous Turns\n",
        "The following turns have SPARQL results that can be reused "
        "with the use_previous_results tool:\n",
    ]
    for turn_num, data in sorted(turn_map.items()):
        query_snippet = data.query[:120]
        lines.append(f"- Turn {turn_num}: {query_snippet}...")
    return "\n".join(lines)


_PHENOBS_PAPERS_DIR = Path(__file__).resolve().parents[1] / "resources" / "phenobs_papers"


def _load_phenobs_papers_content() -> str:
    """Read every first-page PDF in the phenobs_papers directory and return
    their text content as a single formatted string."""
    if not _PHENOBS_PAPERS_DIR.exists():
        return "No PhenObs papers are available. The phenobs_papers directory does not exist."

    from pypdf import PdfReader

    sections: list[str] = []
    for pdf_path in sorted(_PHENOBS_PAPERS_DIR.glob("*.pdf")):
        try:
            reader = PdfReader(pdf_path)
            text = reader.pages[0].extract_text() if reader.pages else ""
            if text.strip():
                sections.append(f"## {pdf_path.stem}\n\n{text.strip()}")
            else:
                sections.append(f"## {pdf_path.stem}\n\n[No extractable text - this may be a poster or scanned image.]")
        except Exception as exc:
            sections.append(f"## {pdf_path.stem}\n\n[Error reading PDF: {exc}]")

    if not sections:
        return "No PhenObs paper PDFs found in the phenobs_papers directory."

    return (
        f"# PhenObs Scientific Publications (first pages of {len(sections)} papers)\n\n"
        + "\n\n---\n\n".join(sections)
    )


def _step_error(exc: Exception) -> str:
    """The error text of a step that raised. It is stored and sent to the client, so
    only a domain exception shows its message."""
    return str(exc) if isinstance(exc, AppException) else "Internal server error"


def _fallback_title(question: str, max_length: int = 60) -> str:
    """The session title when none is generated: the question as one line, cut at a
    word boundary."""
    clean = " ".join(question.split())
    if len(clean) <= max_length:
        return clean
    cut = clean[:max_length]
    space = cut.rfind(" ")
    return (cut[:space] if space > max_length // 2 else cut).rstrip() + "…"


NO_PREVIOUS_DATA_ANSWER = (
    "There are no previous query results available to fall back on. "
    "Please ask a new question."
)
DEFAULT_CLARIFICATION = "Could you phrase your question more precisely?"


class ChatService:
    def __init__(
        self,
        llm: LLMService,
        sparql: SparqlService,
        lucene: LuceneService,
        settings: Settings,
    ):
        self.llm = llm
        self.sparql = sparql
        self.lucene = lucene
        self.settings = settings

    async def run(
        self,
        session_id: uuid.UUID | None,
        message: str,
        repo: ChatRepository,
        state: TurnState,
    ) -> AsyncIterator[ChatEvent]:
        """Run one chat turn as a stream of events, persisting it step by step.

        The repository is passed per run, not held by the service: its DB session has
        to live as long as the stream. Exceptions propagate to the caller; before
        that the assistant message is marked `error`.
        """
        # 1. Session handling. Nothing is written for an unknown id.
        title: str | None = None
        if session_id is None:
            session_id = await repo.create_session()
            logger.info(f"Created new session: {session_id}")
        else:
            sessions = await repo.get_sessions([session_id])
            if not sessions:
                raise SessionNotFoundException(f"Session {session_id} not found")
            title = sessions[0].title

        # A session gets its title on its first turn (or on a later one, if that
        # failed before a title was stored). Without generation the shortened
        # question is the title and already part of the `session` event.
        needs_title = title is None
        if needs_title and not self.settings.generate_session_titles:
            title = _fallback_title(message)
            await repo.set_title(session_id, title, manual=False)
            needs_title = False

        # 2. Load history (last N complete turns) and the reusable-data map
        depth = self.settings.chat_history_depth
        history_msgs = await repo.get_history(session_id, turns=depth)
        history, turn_map = _build_history(history_msgs)

        # 3. Persist the user message and open the assistant message of the turn
        message_id = await repo.start_turn(session_id, message)
        state.message_id = message_id

        # The title is generated next to the turn, so it does not delay the stream.
        title_task: asyncio.Task[str | None] | None = None
        if needs_title:
            title_task = asyncio.create_task(self._generate_title(message))
        try:
            yield SessionEvent(session_id=session_id, message_id=message_id, title=title)
            async for event in self._run_turn(
                session_id, message, history, turn_map, repo, state, title_task
            ):
                yield event
        except Exception:
            # Any exception, not only the infrastructure ones: a bug must not leave
            # a `running` row behind. (A cancellation is not an Exception; the caller
            # handles it.)
            await self._mark_failed(repo, state)
            raise
        finally:
            # A no-op once the title is there; otherwise the run failed or was cancelled.
            if title_task is not None:
                title_task.cancel()

    async def _run_turn(
        self,
        session_id: uuid.UUID,
        message: str,
        history: list[dict[str, str]],
        turn_map: dict[int, TurnData],
        repo: ChatRepository,
        state: TurnState,
        title_task: asyncio.Task[str | None] | None,
    ) -> AsyncIterator[ChatEvent]:
        assert state.message_id is not None
        message_id = state.message_id

        # 4. Seed the conversation for the agentic loop
        system_prompt = self.llm.query_system_prompt() + _available_data_note(turn_map)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": message},
        ]

        # 5. Agentic loop: the model may run several queries (and inspect their
        #    results) before producing a final answer. Track the most recent
        #    query/results: the final answer is written from them.
        last_query = ""
        last_results: str | None = None
        row_count: int | None = None
        answer: str | None = None
        ordinal = 0

        for iteration in range(self.settings.chat_max_tool_iterations):
            # Between iterations: the title, as soon as it is there. Stored through
            # the run's own repository (a DB session must not be used concurrently).
            if title_task is not None and title_task.done():
                title_event = await self._store_title(title_task, session_id, message, repo)
                title_task = None
                if title_event is not None:
                    yield title_event

            # The reasoning of this call is passed on while it is written; the call's
            # last item is what the model decided.
            turn: LLMTurn | None = None
            async for item in self.llm.chat_with_tools(messages, TOOLS):
                if isinstance(item, LLMTurn):
                    turn = item
                else:
                    self._keep_thinking(state, item)
                    yield ThinkingEvent(delta=item)
            assert turn is not None

            # Model stopped calling tools → data gathering is done. Produce the
            # final answer with the dedicated answer prompt rather than using the
            # model's loop text. If no data was ever gathered, fall back to that
            # loop text (the model answered without needing a query).
            if turn.tool_call is None:
                if last_results is None:
                    answer = turn.answer or ""
                break

            tc = turn.tool_call
            logger.info(f"Iteration {iteration + 1}: LLM chose tool '{tc.name}'")

            ordinal += 1
            kind, args = self._plan_step(tc, turn_map)
            # The reasoning so far led to this tool call: it is stored with the step.
            step_id = await repo.start_step(
                message_id,
                ordinal=ordinal,
                kind=kind,
                args=args,
                thinking=state.thinking.strip() or None,
            )
            state.thinking = ""
            yield StepStartedEvent(step_id=step_id, ordinal=ordinal, kind=kind, args=args)

            started = time.monotonic()
            try:
                outcome = await self._execute_step(kind, args, turn_map, repo)
            except Exception as e:
                # Infrastructure failure: close the step, then abort the turn.
                duration_ms = int((time.monotonic() - started) * 1000)
                error = _step_error(e)
                await self._close_failed_step(repo, step_id, error, duration_ms)
                yield StepFinishedEvent(
                    step_id=step_id, ok=False, error=error, duration_ms=duration_ms
                )
                raise
            duration_ms = int((time.monotonic() - started) * 1000)
            await repo.finish_step(
                step_id,
                ok=outcome.ok,
                count=outcome.count,
                result=outcome.result,
                error=outcome.error,
                duration_ms=duration_ms,
            )
            yield StepFinishedEvent(
                step_id=step_id,
                ok=outcome.ok,
                count=outcome.count,
                error=outcome.error,
                duration_ms=duration_ms,
            )

            if outcome.final_answer is not None:
                # Clarification, or nothing to reuse: the fixed text is the answer
                # and no data is attached to it.
                answer, row_count = outcome.final_answer, None
                break
            if outcome.results is not None:
                # Keep the full results for the final answer; only a truncated
                # sample went back into the loop transcript.
                last_query = outcome.query or last_query
                last_results, row_count = outcome.results, outcome.count
            self._append_tool_exchange(messages, tc, outcome.output)
        else:
            # Loop exhausted without a final answer — force one via the answer prompt
            # using whatever data was gathered so far.
            logger.warning(
                f"Tool loop hit max iterations ({self.settings.chat_max_tool_iterations}); forcing final answer"
            )

        # 6. Final answer: streamed from the answer call, or the fixed / loop text
        #    in one piece.
        if answer is None:
            if state.thinking:
                # The answer call's reasoning follows that of the loop's last call.
                state.thinking = state.thinking.rstrip() + "\n\n"
            async for kind, delta in self.llm.generate_answer_stream(
                message, last_query, last_results
            ):
                if kind == "thinking":
                    self._keep_thinking(state, delta)
                    yield ThinkingEvent(delta=delta)
                else:
                    state.answer += delta
                    yield AnswerEvent(delta=delta)
        else:
            state.answer = answer
            yield AnswerEvent(delta=answer)

        # Reasoning that only ended with a lone </think> went out as answer text;
        # it is split off before the message is stored.
        late_thinking, content = split_think(state.answer)
        if not self.settings.persist_thinking:
            late_thinking = None
        thinking = "\n\n".join(
            part for part in (state.thinking.strip(), late_thinking) if part
        )
        await repo.complete_turn(
            session_id, message_id, content=content, thinking=thinking or None
        )

        # A title that is still being generated is waited for (with a timeout), so
        # `session_title` always comes before `done`.
        if title_task is not None:
            title_event = await self._store_title(title_task, session_id, message, repo)
            if title_event is not None:
                yield title_event
        yield DoneEvent(message_id=message_id, row_count=row_count)

    def _keep_thinking(self, state: TurnState, delta: str) -> None:
        """Collect reasoning for storage, unless that is switched off."""
        if self.settings.persist_thinking:
            state.thinking += delta

    async def _generate_title(self, question: str) -> str | None:
        """The generated title, or None if the call failed. Never raises: a title
        must not fail the turn."""
        try:
            return await self.llm.generate_title(question)
        except Exception as e:
            logger.warning(f"Session title generation failed: {e}")
            return None

    async def _store_title(
        self,
        title_task: asyncio.Task[str | None],
        session_id: uuid.UUID,
        question: str,
        repo: ChatRepository,
    ) -> SessionTitleEvent | None:
        """Store the generated title, or the shortened question if generation failed
        or takes longer than the timeout. None if nothing was stored (the session
        was renamed by hand in the meantime). Never raises."""
        try:
            title = await asyncio.wait_for(
                title_task, timeout=self.settings.session_title_timeout
            )
        except asyncio.TimeoutError:
            logger.warning("Session title generation timed out")
            title = None
        title = title or _fallback_title(question)
        try:
            if not await repo.set_title(session_id, title, manual=False):
                return None
        except Exception:
            logger.exception(f"Could not store the title of session {session_id}")
            try:
                await repo.rollback()
            except Exception:
                logger.exception("Rollback after a failed title update failed")
            return None
        return SessionTitleEvent(session_id=session_id, title=title)

    async def _close_failed_step(
        self, repo: ChatRepository, step_id: uuid.UUID, error: str, duration_ms: int
    ) -> None:
        """Store a step that raised as failed. Never raises: the original exception
        is the one the caller has to see."""
        try:
            # The failure may have been a DB error that left the transaction aborted.
            await repo.rollback()
            await repo.finish_step(
                step_id, ok=False, count=None, result=None, error=error,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception(f"Could not close failed step {step_id}")

    async def _mark_failed(self, repo: ChatRepository, state: TurnState) -> None:
        """Set the assistant message to `error`. Never raises: the original exception
        is the one the caller has to see."""
        if state.message_id is None:
            return
        try:
            # The failure may have been a DB error that left the transaction aborted.
            await repo.rollback()
            await repo.fail_message(state.message_id, content=state.answer)
        except Exception:
            logger.exception(f"Could not mark message {state.message_id} as failed")

    def _plan_step(
        self, tc: ToolCallResult, turn_map: dict[int, TurnData]
    ) -> tuple[StepKind, dict[str, Any]]:
        """Map a tool call to the step it becomes: its kind and the cleaned-up
        arguments that are stored, shown and executed."""
        if tc.name == "execute_sparql_query":
            # Safety net: cap an unbounded SELECT so a forgotten LIMIT can't blow up
            # the result payload (and the loop context).
            return "sparql_query", {"query": ensure_limit(tc.arguments.get("query", ""))}

        if tc.name == "resolve_entity":
            try:
                limit = int(tc.arguments.get("limit", 5))
            except (ValueError, TypeError):
                limit = 5
            return "resolve_entity", {
                "term": tc.arguments.get("term", ""),
                "type": tc.arguments.get("type") or None,
                "limit": limit,
            }

        if tc.name == "use_previous_results":
            ref_turn = self._resolve_ref(tc, turn_map)
            args: dict[str, Any] = {"reference_turn": ref_turn}
            ref = turn_map.get(ref_turn)
            if ref is not None:
                # Points at the step that holds the data, so a later turn can reuse
                # it again through this one (see reusable_data).
                args["source_step_id"] = str(ref.step_id)
                args["query"] = ref.query
            return "previous_results", args

        if tc.name == "load_phenobs_papers":
            return "papers", {}

        if tc.name != "ask_clarification":
            # Unknown tool name → treat as clarification rather than crash.
            logger.warning(f"Unknown tool call: {tc.name}")
        return "clarification", {
            "question": tc.arguments.get("question") or DEFAULT_CLARIFICATION
        }

    async def _execute_step(
        self,
        kind: StepKind,
        args: dict[str, Any],
        turn_map: dict[int, TurnData],
        repo: ChatRepository,
    ) -> StepOutcome:
        """Execute a planned step. A problem the model can react to (bad query, no
        Lucene connector) comes back as a failed outcome; infrastructure failures
        are raised and abort the turn."""
        if kind == "sparql_query":
            query = args["query"]
            logger.info(f"Executing SPARQL query: {query}")
            try:
                results = await self.sparql.execute(query)
            except SparqlQueryException as e:
                # Bad query → hand the error back to the model so it can fix it
                # in the next loop iteration.
                logger.info(f"Query failed; returning error to LLM for retry: {e}")
                return StepOutcome(
                    ok=False,
                    error=str(e),
                    output=(
                        f"The SPARQL query FAILED and was not executed. Error:\n{e}\n\n"
                        "Revise the query and call execute_sparql_query again."
                    ),
                )
            stored = results_to_json(results)
            return StepOutcome(
                ok=True,
                count=count_rows(stored),
                result=stored,
                output=_truncate_results(results),
                query=query,
                results=results,
            )

        if kind == "resolve_entity":
            term, etype = args["term"], args["type"]
            logger.info(f"Resolving entity: term={term!r} type={etype!r}")
            try:
                candidates = await self.lucene.search(term, etype, args["limit"])
            except SparqlQueryException as e:
                # e.g. the Lucene connector isn't set up → let the model fall back
                # to a label FILTER.
                logger.info(f"Entity resolution unavailable: {e}")
                return StepOutcome(
                    ok=False,
                    error=str(e),
                    output=(
                        "Entity resolution is unavailable. Fall back to a SPARQL query "
                        'that matches labels directly, e.g. '
                        'FILTER(CONTAINS(LCASE(?label), "...")).'
                    ),
                )
            return StepOutcome(
                ok=True,
                count=len(candidates),
                result=candidates,
                output=_format_candidates(term, candidates),
            )

        if kind == "previous_results":
            ref = turn_map.get(args["reference_turn"])
            stored_step = await repo.get_step_result(ref.step_id) if ref else None
            if ref is None or stored_step is None or stored_step[1] is None:
                return StepOutcome(
                    ok=False,
                    error="No previous query results available.",
                    final_answer=NO_PREVIOUS_DATA_ANSWER,
                )
            # No `result`: it would duplicate the referenced step.
            results = results_to_text(stored_step[1])
            return StepOutcome(
                ok=True,
                count=count_rows(stored_step[1]),
                output=_truncate_results(results),
                query=ref.query,
                results=results,
            )

        if kind == "papers":
            logger.info("Loading PhenObs paper contents into context")
            return StepOutcome(ok=True, output=_load_phenobs_papers_content())

        return StepOutcome(ok=True, final_answer=args["question"])

    def _append_tool_exchange(
        self, messages: list[dict[str, Any]], tc: ToolCallResult, output: str
    ) -> None:
        """Append the assistant tool call + its result to the running transcript
        so the model can decide its next step."""
        if tc.tool_call_id:
            # Proper structured round-trip: assistant tool_calls msg + tool reply.
            # Restrict the dumped message to the single tool_call we're answering:
            # a model may emit several in one message, but we only reply to one, and
            # OpenAI requires every tool_call to have a matching tool response.
            msg_dict = tc.raw_message.model_dump()
            if msg_dict.get("tool_calls"):
                msg_dict["tool_calls"] = [
                    c for c in msg_dict["tool_calls"] if c.get("id") == tc.tool_call_id
                ]
            messages.append(msg_dict)
            messages.append(
                {"role": "tool", "tool_call_id": tc.tool_call_id, "content": output}
            )
        else:
            # Text-recovered call has no valid id, so a `role: tool` message would
            # be rejected. Replay the model's own output, then feed results back.
            messages.append({"role": "assistant", "content": tc.raw_message.content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool `{tc.name}` returned:\n\n{output}",
                }
            )

    def _resolve_ref(self, tc: ToolCallResult, turn_map: dict[int, TurnData]) -> int:
        """The turn referenced by use_previous_results, falling back to the most
        recent turn that has data. Without any data the requested number is kept."""
        try:
            ref_turn = int(tc.arguments.get("reference_turn", 0))
        except (ValueError, TypeError):
            ref_turn = 0

        if ref_turn not in turn_map and turn_map:
            logger.warning(
                f"use_previous_results referenced turn {ref_turn}, not found. "
                f"Falling back to latest. Available: {sorted(turn_map.keys())}"
            )
            ref_turn = max(turn_map.keys())
        return ref_turn

    async def models(self) -> ModelResponse:
        return await self.llm.get_models()

    async def get_full_table(self, limit: int | None) -> FullTableResponse:
        # No kwargs: the SPARQL query contains literal braces that would break str.format.
        query = load_prompt(self.settings.full_table_query_path)
        if limit is not None:
            query = f"{query.rstrip()}\nLIMIT {int(limit)}"
        raw_results = await self.sparql.execute(query)
        table = parse_sparql_bindings(raw_results, self.settings.full_table_columns)
        return FullTableResponse(full_table=FullTable(**table))
