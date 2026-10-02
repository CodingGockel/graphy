# API

Base URL: `/api/v1` (locally `http://localhost:8000/api/v1`). Schemas live in
`backend/src/models/schemas.py`, the chat events in `backend/src/models/events.py`. Always up-to-date interactive docs: `http://localhost:8000/docs`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/chat` | Ask a question (creates a session if needed). Answers as an event stream. |
| `GET` | `/session/{id}/history` | Full history of a session. |
| `DELETE` | `/session/{id}` | Delete a session. |
| `GET` | `/health` | Status of GraphDB and the LLM API. |
| `GET` | `/chat/models` | Models available on the LLM API. |
| `GET` | `/chat/full_table` | Fixed tabular view (PhenObs-specific, not used by the frontend). |

**Errors:**

- **Shape:** every error body is `{ "status": "error", "error": "short message", "detail": "..." }`.
- **Codes:** `502` means an upstream service answered with an error, `503` means a dependency is
  unreachable, `404` means an unknown session, `422` means an invalid request.
- **Chat stream:** `POST /chat` reports failures after its first byte as an `error` event instead
  (see below).

## Chat

### `POST /chat`

```jsonc
// request
{ "message": "When did Tulipa sylvestris first flower in Jena in 2024?", "session_id": null }
```

The response is a stream of **Server-Sent Events** (`text/event-stream`), one frame per event:

```
event: session
data: {"session_id":"3f1d…-9ac2","message_id":"8b0e…","title":null}

event: step_started
data: {"step_id":"51c7…","ordinal":1,"kind":"sparql_query","args":{"query":"SELECT …"}}

event: step_finished
data: {"step_id":"51c7…","ok":true,"count":1,"error":null,"duration_ms":412}

event: answer
data: {"delta":"On day 87 of the year — 27 March 2024."}

event: done
data: {"message_id":"8b0e…","row_count":1}
```

| Event | Fields | Meaning |
|-------|--------|---------|
| `session` | `session_id`, `message_id`, `title` | Always first. `message_id` is the assistant message; `title` may be `null`. |
| `session_title` | `session_id`, `title` | The session got a title (not sent yet). |
| `step_started` | `step_id`, `ordinal`, `kind`, `args` | A tool call begins. `kind`: `resolve_entity`, `sparql_query`, `previous_results`, `papers`, `clarification`. |
| `step_finished` | `step_id`, `ok`, `count`, `error`, `duration_ms` | The tool call ended. `count` is the number of rows or candidates; `error` is set when `ok` is `false`. |
| `thinking` | `delta` | A piece of the model's reasoning (not sent yet). It belongs to whatever comes next: the following step, or the answer. |
| `answer` | `delta` | A piece of the answer; append the deltas. Currently one event with the whole text. |
| `done` | `message_id`, `row_count` | The turn is complete. `row_count` is that of the data the answer is based on. |
| `error` | `kind`, `message` | The turn failed. Ends the stream; no `done` follows. |

Order of a turn: `session` → (`step_started` → `step_finished`)\* → `answer`+ → `done`.

How a client should use it:

1. **Transport:** read the body as a stream (`fetch` + `ReadableStream`; `EventSource` cannot
   `POST`). Frames are separated by a blank line. Lines starting with `:` are comments: the backend
   sends `: ping` every 15 s while nothing else happens, to keep proxies from closing the stream.
2. **First message:** send `session_id: null`. The backend creates a session.
3. **Every message:** take `session_id` from the `session` event and send it next time.
   - **Unknown IDs:** an ID the backend doesn't know is a `404` with a normal JSON error body;
     nothing is created or stored. Start a new session by sending `session_id: null`.
4. **Errors:** the status code is decided before the stream starts, so `404` and `422` are the
   only HTTP errors. Everything after that is `200` plus an `error` event, whose `kind` matches
   the HTTP errors of the other routes:

   | `kind` | Meaning | Elsewhere |
   |--------|---------|-----------|
   | `llm_unavailable` | The LLM API is unreachable. | `503` |
   | `llm_no_content` | The LLM returned nothing usable. | `502` |
   | `sparql_unavailable` | GraphDB is unreachable. | `503` |
   | `sparql_failed` | GraphDB answered with an error. | `502` |
   | `internal` | Anything else (logged on the server). | `500` |

   A stream that ends without `done` or `error` is a failure as well (connection lost).
5. **Cancelling:** close the connection. The backend stops the turn and stores it as `aborted`
   with the answer text sent so far; steps that already ran are kept.
6. **Clarifications:** when the LLM needs more information, its question simply arrives as
   `answer` (after a step of the kind `clarification`). Reply on the same session.
7. **Query results:** results are never part of an event. A step's `count` says how many rows it
   found; the data itself is available through the session history.
8. **Reasoning:** `answer` can contain a `<think>…</think>` block (or text before a lone
   `</think>`) when the model answered without tools. Split it off before rendering (the frontend
   does this in `src/lib/thinking.ts`).

### `GET /chat/models`

`{ "models": ["alias-huge", …] }`, or `503` if the LLM API is unreachable.

### `GET /chat/full_table?limit=N`

Runs the fixed query from `FULL_TABLE_QUERY_PATH` (no LLM) and returns
`{ "full_table": { "columns": [...], "rows": [{...}] } }`. Numeric cells are typed; missing cells are
`null`. This endpoint is specific to the PhenObs KG.

## Sessions

### `GET /session/{id}/history`

```jsonc
{
  "session_id": "3f1d…-9ac2",
  "messages": [
    { "role": "user", "content": "…", "sparql_query": null, "sparql_results": null, "created_at": "2026-10-01T17:13:47Z" },
    { "role": "assistant", "content": "…", "sparql_query": "SELECT …", "sparql_results": "{…}", "created_at": "…" }
  ]
}
```

`404` if the session doesn't exist. The frontend uses this both to open a session and to validate
"Add session".

`sparql_query` and `sparql_results` come from the turn's last successful query step, or from the
query step whose results the turn reused; they are `null` when the turn used no data.

### `DELETE /session/{id}`

Deletes the session with its messages and steps. `204`, or `404` if unknown.

## Health

### `GET /health`

```jsonc
{
  "status": "ok",                 // ok | degraded | down (worst of all services)
  "error": null,                  // "service: error; …" or null
  "services": {
    "sparql_service": { "status": "ok", "error": null, "additional_attributes": { … } },
    "llm_service":    { "status": "ok", "error": null, "additional_attributes": { … } }
  }
}
```

Returns `200` when everything is `ok` and `503` otherwise. The body is a full health response in both
cases, so read it even on 503. This check also pings the LLM API, so don't poll it aggressively.
