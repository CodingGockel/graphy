import json
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.schemas import ChatRequest, ChatResponse, ModelResponse, FullTable, FullTableResponse
from src.util.sparql_utils import ensure_limit, extract_sparql_query, parse_sparql_bindings
from src.db.models import Message
from src.db.repository import ChatRepository
from src.services.llm_service import LLMService, ToolCallResult
from src.services.sparql_service import SparqlService
from src.services.lucene_service import LuceneService
from src.util.exceptions import SparqlQueryException
from src.util.config import Settings
from src.util.logger import logger
from src.util.llm_utils import load_tools, load_prompt

TOOLS: list[dict[str, Any]] = load_tools()

def _build_history(
    messages: list[Message],
) -> tuple[list[dict[str, str]], dict[int, Message]]:
    """Convert DB messages into LLM message dicts and a turn->Message map for data reuse."""
    llm_messages: list[dict[str, str]] = []
    turn_map: dict[int, Message] = {}
    turn = 0

    for msg in messages:
        if msg.role == "user":
            turn += 1
            llm_messages.append({"role": "user", "content": msg.content})
        elif msg.role == "assistant":
            llm_messages.append({"role": "assistant", "content": msg.content})
            if msg.sparql_results:
                turn_map[turn] = msg

    return llm_messages, turn_map


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


def _available_data_note(turn_map: dict[int, Message]) -> str:
    if not turn_map:
        return ""
    lines = [
        "\n\n# Reusable Data from Previous Turns\n",
        "The following turns have SPARQL results that can be reused "
        "with the use_previous_results tool:\n",
    ]
    for turn_num, msg in sorted(turn_map.items()):
        query_snippet = (msg.sparql_query or "")[:120]
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


class ChatService:
    def __init__(
        self,
        llm: LLMService,
        sparql: SparqlService,
        lucene: LuceneService,
        db: AsyncSession,
        settings: Settings,
    ):
        self.llm = llm
        self.sparql = sparql
        self.lucene = lucene
        self.repo = ChatRepository(db)
        self.settings = settings

    async def process(self, request: ChatRequest) -> ChatResponse:
        # 1. Session handling
        if request.session_id is None:
            session_id = await self.repo.create_session()
            logger.info(f"Created new session: {session_id}")
        elif not await self.repo.session_exists(request.session_id):
            session_id = await self.repo.create_session()
            logger.info(f"Session {request.session_id} not found, created new: {session_id}")
        else:
            session_id = request.session_id

        # 2. Load history (last N turns) and the reusable-data map
        depth = self.settings.chat_history_depth
        history_msgs = await self.repo.get_history(session_id, limit=depth)
        history, turn_map = _build_history(history_msgs)

        # 3. Persist the user message
        await self.repo.save_message(
            session_id=session_id, role="user", content=request.message
        )

        # 4. Seed the conversation for the agentic loop
        system_prompt = self.llm.query_system_prompt() + _available_data_note(turn_map)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": request.message},
        ]

        # 5. Agentic loop: the model may run several queries (and inspect their
        #    results) before producing a final answer. Track the most recent
        #    query/results for the response payload.
        last_query = ""
        last_results: str | None = None

        for iteration in range(self.settings.chat_max_tool_iterations):
            turn = await self.llm.chat_with_tools(messages, TOOLS)

            # Model stopped calling tools → data gathering is done. Produce the
            # final answer with the dedicated answer prompt rather than using the
            # model's loop text. If no data was ever gathered, fall back to that
            # loop text (the model answered without needing a query).
            if turn.tool_call is None:
                if last_results is None:
                    return await self._finalize(
                        session_id, turn.answer or "", last_query, last_results
                    )
                answer = await self.llm.generate_answer(
                    request.message, last_query, last_results
                )
                return await self._finalize(session_id, answer, last_query, last_results)

            tc = turn.tool_call
            logger.info(f"Iteration {iteration + 1}: LLM chose tool '{tc.name}'")

            if tc.name == "ask_clarification":
                return await self._handle_clarification(session_id, tc)

            if tc.name == "execute_sparql_query":
                # Safety net: cap an unbounded SELECT so a forgotten LIMIT can't blow up
                # the result payload (and the loop context).
                query = ensure_limit(tc.arguments.get("query", ""))
                logger.info(f"Executing SPARQL query: {query}")
                try:
                    results = await self.sparql.execute(query)
                except SparqlQueryException as e:
                    # Bad query → hand the error back to the model so it can fix it
                    # in the next loop iteration. Infra failures are not caught here
                    # and still abort the request.
                    logger.info(f"Query failed; returning error to LLM for retry: {e}")
                    self._append_tool_exchange(
                        messages,
                        tc,
                        f"The SPARQL query FAILED and was not executed. Error:\n{e}\n\n"
                        "Revise the query and call execute_sparql_query again.",
                    )
                    continue
                # Keep the full results for the final answer; feed only a truncated
                # sample back into the loop transcript.
                last_query, last_results = query, results
                self._append_tool_exchange(messages, tc, _truncate_results(results))
                continue

            if tc.name == "resolve_entity":
                term = tc.arguments.get("term", "")
                etype = tc.arguments.get("type") or None
                try:
                    limit = int(tc.arguments.get("limit", 5))
                except (ValueError, TypeError):
                    limit = 5
                logger.info(f"Resolving entity: term={term!r} type={etype!r}")
                try:
                    candidates = await self.lucene.search(term, etype, limit)
                except SparqlQueryException as e:
                    # e.g. the Lucene connector isn't set up → let the model fall back
                    # to a label FILTER. Infra failures are not caught and still abort.
                    logger.info(f"Entity resolution unavailable: {e}")
                    self._append_tool_exchange(
                        messages,
                        tc,
                        "Entity resolution is unavailable. Fall back to a SPARQL query "
                        'that matches labels directly, e.g. '
                        'FILTER(CONTAINS(LCASE(?label), "...")).',
                    )
                    continue
                self._append_tool_exchange(messages, tc, _format_candidates(term, candidates))
                continue

            if tc.name == "use_previous_results":
                ref_msg = self._resolve_ref(tc, turn_map)
                if ref_msg is None:
                    return await self._no_previous_data(session_id)
                last_query = ref_msg.sparql_query or last_query
                last_results = ref_msg.sparql_results or last_results
                self._append_tool_exchange(
                    messages, tc, _truncate_results(ref_msg.sparql_results or "")
                )
                continue

            if tc.name == "load_phenobs_papers":
                logger.info("Loading PhenObs paper contents into context")
                content = _load_phenobs_papers_content()
                self._append_tool_exchange(messages, tc, content)
                continue

            # Unknown tool name → treat as clarification rather than crash.
            logger.warning(f"Unknown tool call: {tc.name}")
            return await self._handle_clarification(session_id, tc)

        # Loop exhausted without a final answer — force one via the answer prompt
        # using whatever data was gathered so far.
        logger.warning(
            f"Tool loop hit max iterations ({self.settings.chat_max_tool_iterations}); forcing final answer"
        )
        answer = await self.llm.generate_answer(request.message, last_query, last_results)
        return await self._finalize(session_id, answer, last_query, last_results)

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

    def _resolve_ref(
        self, tc: ToolCallResult, turn_map: dict[int, Message]
    ) -> Message | None:
        """Resolve the turn referenced by use_previous_results, falling back to
        the most recent turn that has data."""
        try:
            ref_turn = int(tc.arguments.get("reference_turn", 0))
        except (ValueError, TypeError):
            ref_turn = 0

        ref_msg = turn_map.get(ref_turn)
        if ref_msg is None and turn_map:
            logger.warning(
                f"use_previous_results referenced turn {ref_turn}, not found. "
                f"Falling back to latest. Available: {sorted(turn_map.keys())}"
            )
            ref_msg = turn_map[max(turn_map.keys())]
        return ref_msg

    async def _finalize(
        self,
        session_id,
        answer: str,
        last_query: str,
        last_results: str | None,
    ) -> ChatResponse:
        await self.repo.save_message(
            session_id=session_id,
            role="assistant",
            content=answer,
            sparql_query=last_query or None,
            sparql_results=last_results,
        )
        return ChatResponse(
            answer=answer,
            session_id=session_id,
            llm_generated_query=last_query,
            sparql_query_result=last_results,
        )

    async def _no_previous_data(self, session_id) -> ChatResponse:
        answer = (
            "There are no previous query results available to fall back on. "
            "Please ask a new question."
        )
        return await self._finalize(session_id, answer, "", None)

    async def _handle_clarification(self, session_id, tc: ToolCallResult) -> ChatResponse:
        question = tc.arguments.get("question") or "Could you phrase your question more precisely?"
        return await self._finalize(session_id, question, "", None)

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
