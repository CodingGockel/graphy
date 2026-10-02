# Backend rework: tickets

The rework from [`../streaming-rework.md`](../streaming-rework.md) (one-shot JSON response → SSE
event stream, new session/chat persistence), cut into small tickets. One ticket = one change.
Where a ticket and the original plan disagree, **the ticket wins**; the refinements are listed below.

Working mode: Claude implements one ticket (code, tests, docs) and stops. Mo runs `pytest`,
`mypy src/`, `npm run check` and the app, then sets the status here.

| # | Ticket | Area | Status |
|---|--------|------|--------|
| 01 | [Small fixes](./01-small-fixes.md) | backend | open |
| 02 | [Data layer: sessions, messages, steps](./02-data-layer.md) | backend | open |
| 03 | [Chat event types](./03-chat-events.md) | backend | open |
| 04 | [ChatService as event generator](./04-chat-service-generator.md) | backend | open |
| 05 | [SSE chat route](./05-sse-chat-route.md) | backend | open |
| 06 | [Frontend: SSE client](./06-frontend-sse-client.md) | frontend | open |
| 07 | [Session API](./07-session-api.md) | backend | open |
| 08 | [Frontend: session endpoints](./08-frontend-sessions.md) | frontend | open |
| 09 | [Session titles](./09-session-titles.md) | backend + frontend | open |
| 10 | [Answer token streaming](./10-answer-streaming.md) | backend | open |
| 11 | [Tool-loop streaming and thinking](./11-tool-loop-streaming.md) | backend | open |
| 12 | [Frontend: trace (steps and reasoning)](./12-frontend-trace.md) | frontend | open |

The app stays runnable after every ticket, with two pairs that must land together because the
backend contract changes under the frontend: **05 + 06** and **07 + 08**. Ticket 12 only needs
06 + 08 and can land before 10 and 11; it then shows reasoning as soon as those start emitting it.

## Refinements over the original plan

Decided on 2026-10-01 while reviewing the plan against the current code.

1. **The frontend exists and consumes the old API.** The plan assumed it did not. The series
   therefore includes minimal frontend tickets that bind the new contract (06, 08) and one that
   shows the trace (12).
2. **No global session list.** `GET /sessions` without auth would show every visitor all chats. The
   browser keeps its session IDs in `localStorage` (as today); the backend serves titles and
   metadata for a given set of IDs (`GET /sessions?ids=…`). "Add session by ID" keeps working.
3. **`use_previous_results` reads from `steps`.** The `messages.sparql_query` / `sparql_results`
   columns go away; the reusable-data map is built from the last successful `sparql_query` step of
   each turn.
4. **Message status gets `running`.** The assistant message row is created at the start of the turn
   (steps reference it, the `session` event carries its ID): `running | complete | aborted | error`.
   A `running` row left behind by a crash is reported as `aborted` on read; there is no cleanup job.
5. **Only complete turns go into the LLM history.** Turns whose assistant message is not `complete`
   are skipped as a pair (user + assistant).
6. **Unknown `session_id` on `POST /chat` is a 404**, no longer a silently created new session.
7. **Abort is cancellation, not polling.** Starlette cancels the response generator when the client
   disconnects. The work is to mark the message `aborted` through a fresh DB session, shielded from
   that cancellation. No `request.is_disconnected()` polling.
8. **Heartbeat via producer task + queue.** `asyncio.wait_for` around the generator would cancel it
   on timeout. The route runs the service in a task that feeds an `asyncio.Queue`; the response
   generator reads the queue with a timeout and emits `: ping` when it expires.
9. **Loop text is buffered, not streamed as thinking.** In the tool loop, only `<think>` content is
   streamed live. Other content is buffered because it may turn out to be a text-encoded tool call
   or, when no query ran, the final answer (then emitted as `answer`).
10. **Tests per ticket**, not as a final block.
11. **`SparqlService.aclose()` stays.** The plan called it unused; `lucene_setup.py` calls it on a
    client it owns.

Added on 2026-10-01 for the trace in the frontend (ticket 12):

12. **The frontend shows everything.** Every tool call and every reasoning part is a collapsible
    item in the answer bubble, live and after a reload. Ticket 11 is therefore no longer optional.
13. **Reasoning is stored per step.** `steps.thinking` holds the reasoning that led to that tool
    call; `messages.thinking` holds only the reasoning before the final answer. A single text
    field per message would lose the order after a reload.
14. **`count` instead of `summary`.** Steps carry a number (rows, candidates) instead of an English
    summary string, so the frontend can label them in all three locales. `step_finished` also
    carries the `error` text of a failed step.
15. **Step results are shown too**, loaded lazily via `GET /steps/{id}/result` when a step is
    expanded (the plan's reason for not streaming them still holds).

Added on 2026-10-01 from a review of the tickets against the code:

16. **The streaming splitter ignores a lone `</think>`.** It cannot be handled incrementally; a
    whole-text split fixes it up before the message is stored (ticket 10).
17. **`chat_with_tools()` becomes a generator**, not a callback, with a setting to switch
    tool-loop streaming off (ticket 11).
18. **Step results are never loaded with the history**, only on demand; the turn map is keyed on
    `messages.turn` (ticket 02).
19. **Unique constraints** on `(session_id, turn, role)` and `(message_id, ordinal)`; every
    repository method ends its transaction (ticket 02).
20. **Any exception marks the message `error`**; a failed turn without content is hidden as a
    pair in the frontend (tickets 04, 08).
21. **Leaner events:** `done` without `status`, `error` without `recoverable` (ticket 03).
22. **The health check keeps a short timeout**, independent of `sparql_timeout` (ticket 01).

Unchanged from the plan: no `/api/v2`, no Alembic (drop the DB volume), the agent loop's logic and
prompts stay as they are, deployment config is out of scope.
