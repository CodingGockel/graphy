# API

Base URL: `/api/v1` (locally `http://localhost:8000/api/v1`). Schemas live in
`backend/src/models/schemas.py`, the chat events in `backend/src/models/events.py`. Always up-to-date interactive docs: `http://localhost:8000/docs`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/chat` | Ask a question (creates a session if needed). Answers as an event stream. |
| `GET` | `/sessions?ids=…` | Metadata of the given sessions. |
| `GET` | `/sessions/{id}` | Full history of a session, with the steps of each answer. |
| `PATCH` | `/sessions/{id}` | Rename a session. |
| `DELETE` | `/sessions/{id}` | Delete a session. |
| `GET` | `/steps/{id}/result` | The result of one tool step. |
| `GET` | `/health` | Status of GraphDB and the LLM API. |
| `GET` | `/models` | Models available on the LLM API. |

**Errors:**

- **Shape:** every error body is `{ "status": "error", "error": "short message", "detail": "..." }`.
- **Codes:** `502` means an upstream service answered with an error, `503` means a dependency is
  unreachable, `404` means an unknown session or step, `422` means an invalid request.
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
| `session` | `session_id`, `message_id`, `title` | Always first. `message_id` is the assistant message; `title` is `null` while the title is still being generated (a `session_title` follows). |
| `session_title` | `session_id`, `title` | The session got its title. Sent once, on the turn that gives a session its title (normally the first), anywhere after `session` and always before `done`. |
| `step_started` | `step_id`, `ordinal`, `kind`, `args` | A tool call begins. `kind`: `resolve_entity`, `sparql_query`, `previous_results`, `clarification`. |
| `step_finished` | `step_id`, `ok`, `count`, `error`, `duration_ms` | The tool call ended. `count` is the number of rows or candidates; `error` is set when `ok` is `false`. |
| `thinking` | `delta` | A piece of the model's reasoning, sent while it is written. It belongs to whatever comes next: the following `step_started`, or the answer. Append consecutive deltas. |
| `answer` | `delta` | A piece of the answer; append the deltas. An answer written from query results arrives token by token; a clarification, a fixed text or an answer without a query is one event. |
| `done` | `message_id`, `row_count` | The turn is complete. `row_count` is that of the data the answer is based on. |
| `error` | `kind`, `message` | The turn failed. Ends the stream; no `done` follows. |

Order of a turn: `session` → (`step_started` → `step_finished`)\* → `answer`+ → `done`, with
`thinking` anywhere before a step or the answer and `session_title` anywhere after `session`.

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
   | `session_not_found` | The session was deleted while the turn started. | `404` |
   | `internal` | Anything else (logged on the server). | `500` |

   A stream that ends without `done` or `error` is a failure as well (connection lost).
5. **Cancelling:** close the connection. The backend stops the turn and stores it as `aborted`
   with the answer text sent so far; steps that already ran are kept.
6. **Clarifications:** when the LLM needs more information, its question simply arrives as
   `answer` (after a step of the kind `clarification`). Reply on the same session.
7. **Query results:** results are never part of an event. A step's `count` says how many rows it
   found; the data itself is loaded with `GET /steps/{id}/result`.
8. **Titles:** the title is written by the LLM from the first question, next to the turn. If
   that fails or takes too long, the shortened question is used; with `GENERATE_SESSION_TITLES`
   off it always is, and then it is already part of the `session` event. A title set with
   `PATCH /sessions/{id}` is never overwritten.
9. **Reasoning:** the model's reasoning arrives as `thinking` events: during the tool loop
   (unless `LLM_STREAM_TOOL_LOOP` is off; then in one piece per call) and before the answer. One
   reply of the model may start several steps; its reasoning comes before the first of them. It is
   stored with the step it led to (`steps[].thinking`) or, for the reasoning before the answer,
   with the message (`thinking`), unless `PERSIST_THINKING` is off. One case cannot be detected
   while streaming: a model whose output only *ends* its reasoning with a lone `</think>`. That
   text arrives as `answer` deltas; split it off on the accumulated text (the frontend does this
   in `src/lib/thinking.ts`). The stored message has it split correctly.

## Sessions

There is deliberately **no** endpoint that lists all sessions: without authentication every visitor
would see every chat. A client keeps the IDs of its own sessions and asks for their metadata.

### `GET /sessions?ids=a,b,c`

```jsonc
[
  { "id": "3f1d…-9ac2", "title": "Tulipa in Jena", "updated_at": "2026-10-01T17:13:47Z", "message_count": 4 }
]
```

Metadata for the given IDs, most recently updated first. `ids` is required: comma-separated UUIDs,
at most 100 (`422` otherwise). Unknown IDs are simply left out, so a client can tell which of its
sessions no longer exist. `title` is `null` until the session has one; `updated_at` is bumped when
a turn completes.

### `GET /sessions/{id}`

```jsonc
{
  "id": "3f1d…-9ac2",
  "title": null,
  "updated_at": "2026-10-01T17:13:47Z",
  "messages": [
    { "id": "…", "turn": 1, "role": "user", "content": "…", "thinking": null,
      "status": "complete", "created_at": "…", "steps": [] },
    { "id": "8b0e…", "turn": 1, "role": "assistant", "content": "…", "thinking": null,
      "status": "complete", "created_at": "…",
      "steps": [
        { "id": "51c7…", "ordinal": 1, "kind": "sparql_query", "args": { "query": "SELECT …" },
          "thinking": null, "ok": true, "count": 1, "error": null, "duration_ms": 412 }
      ] }
  ]
}
```

The full history in chronological order; `404` if the session doesn't exist.

- **Turns:** a user message and its answer share a `turn` number. Every turn is returned, also
  failed and aborted ones; `status` of the assistant message says which (`running`, `complete`,
  `aborted`, `error`). User messages are always `complete`.
- **`running`:** a turn that is still in progress, e.g. in another tab. A `running` message older
  than 10 minutes is reported as `aborted` (its turn died with the server).
- **Steps:** the tool calls of the turn, with the same fields as the `step_started` /
  `step_finished` events plus `thinking`. `ok`, `count` and `duration_ms` are `null` for a step
  that never finished. Results are not included.

### `PATCH /sessions/{id}`

`{ "title": "…" }` (1–200 characters, surrounding whitespace is removed). Returns the session's
metadata as in `GET /sessions`; `404` if unknown. A title set this way is never overwritten by a
generated one.

### `DELETE /sessions/{id}`

Deletes the session with its messages and steps. `204`, or `404` if unknown.

### `GET /steps/{id}/result`

```jsonc
{ "step_id": "51c7…", "kind": "sparql_query", "result": { "head": { "vars": […] }, "results": { "bindings": […] } } }
```

The stored result of one step; `404` if the step doesn't exist. `kind` decides the shape:
standard SPARQL JSON for `sparql_query`, a list of `{ uri, label, score }` for `resolve_entity` (`label` holds all labels of the entity, joined with ` | `),
`null` for every other kind and for a failed step. A `previous_results` step has no result of its
own; its `args.source_step_id` names the step that holds the data.

## Models

### `GET /models`

`{ "models": ["alias-huge", …] }`, or `503` if the LLM API is unreachable.

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
