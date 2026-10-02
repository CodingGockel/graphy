# 04: ChatService as event generator

**Depends on:** 02, 03 · **Area:** backend · **the riskiest ticket**

## Goal

Turn the control structure of the agent loop from "return a response" into "yield events", and
persist every step as it happens. The loop's logic (tools, retry on a bad query, `ensure_limit`,
`_truncate_results`, the iteration cap) is not changed.

```python
# before
async def process(self, request: ChatRequest) -> ChatResponse
# after
async def run(self, session_id: UUID | None, message: str, repo: ChatRepository, state: TurnState) -> AsyncIterator[ChatEvent]
```

## Changes

- `ChatService.__init__` no longer takes `db`; the repository is passed per run (needed for 05,
  where the DB session must live inside the stream). `models()` and `get_full_table()` are
  unaffected by that.
- `TurnState`: a small dataclass owned by the caller (`message_id`, `answer`, `thinking`) that
  `run()` keeps up to date. Ticket 05 reads it to store an aborted turn.
- `run()`:
  1. `session_id is None` → create the session. Unknown ID → raise new `SessionNotFoundException`
     (`util/exceptions.py`, mapped to 404 in `exception_handlers.py`) before anything is written.
  2. Load history (complete turns only), write the user message, create the assistant message with
     `status="running"`, `yield SessionEvent`.
  3. Per tool call: `start_step` + `yield StepStarted`, execute, `finish_step` + `yield
     StepFinished`. The existing `logger.info` lines mark the emit points.
     - `sparql_query`: result stored in `steps.result`; a `SparqlQueryException` finishes the step
       with `ok=false` + `error` and feeds the error back to the model as today.
     - `resolve_entity`: candidates in `result`. `papers`: no result. `clarification`: the question
       in `args`.
     - `previous_results`: resolved through the turn map built from steps (keyed on
       `messages.turn`), the result loaded with `get_step_result`; no data → step `ok=false`,
       then the existing fixed answer text.
  4. Final answer as **one** `AnswerDelta` with the full text (token streaming is ticket 10), then
     `finish_message(status="complete")`, `touch_session`, `yield Done`.
- `count` is the number of rows (`sparql_query`, `previous_results`) or candidates
  (`resolve_entity`); a failed step carries its `error` text in `step_finished`. No English
  summary strings: the frontend labels steps itself.
- `previous_results` stores no `result` (it would duplicate the referenced step); the resolved
  turn goes into `args`.
- `_finalize`, `_no_previous_data`, `_handle_clarification` collapse into the generator's exit path.
- Exceptions still propagate out of the generator; before re-raising, the message is set to
  `status="error"`. This holds for **any** exception, not only the infrastructure ones: a bug
  must not leave a `running` row behind.

## Keeping the app runnable

`POST /chat` stays a JSON endpoint for now: the route opens a DB session, consumes `run()` and
assembles the old `ChatResponse` from the events (`session` → `session_id`, `answer` deltas →
`answer`; last `sparql_query` step → `llm_generated_query` / `sparql_query_result` read back via
`get_step_result`). This adapter is the "simple consumer" the plan asks for and is deleted in 05.
`get_chat_service` in `dependencies.py` drops the `db` dependency.

## Tests

Rewrite `test_chat_service.py` around event sequences (mocked LLM, SPARQL, Lucene, repo):

- plain answer without a query; one query; bad query then a corrected query (two steps, first
  `ok=false`); `resolve_entity` with and without the Lucene connector; `use_previous_results` with
  and without data; clarification; unknown tool; iteration cap.
- persistence: each step is started and finished; an infrastructure error and an unexpected
  exception both leave the message at `error` and the earlier steps finished.
- history: non-complete turns are not sent to the LLM.

Adapt `test_chat_router.py` to the adapter.

## Docs

- `docs/architecture.md`: the loop now emits events and persists steps.
