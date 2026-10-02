# API

Base URL: `/api/v1` (locally `http://localhost:8000/api/v1`). Schemas live in
`backend/src/models/schemas.py`. Always up-to-date interactive docs: `http://localhost:8000/docs`.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/chat` | Ask a question (creates a session if needed). |
| `GET` | `/session/{id}/history` | Full history of a session. |
| `DELETE` | `/session/{id}` | Delete a session. |
| `GET` | `/health` | Status of GraphDB and the LLM API. |
| `GET` | `/chat/models` | Models available on the LLM API. |
| `GET` | `/chat/full_table` | Fixed tabular view (PhenObs-specific, not used by the frontend). |

**Errors:**

- **Shape:** every error body is `{ "status": "error", "error": "short message", "detail": "..." }`.
- **Codes:** `502` means an upstream service answered with an error, `503` means a dependency is
  unreachable, `404` means an unknown session, `422` means an invalid request.

## Chat

### `POST /chat`

```jsonc
// request
{ "message": "When did Tulipa sylvestris first flower in Jena in 2024?", "session_id": null }

// response 200
{
  "answer": "On day 87 of the year — 27 March 2024.",
  "session_id": "3f1d…-9ac2",
  "llm_generated_query": "SELECT … ",          // "" if no query ran
  "sparql_query_result": "{\"head\":{…},…}"     // JSON string, null if no query ran
}
```

How a client should use it:

1. **First message:** send `session_id: null`. The backend creates a session.
2. **Every message:** take `session_id` from the response and send it next time.
   - **Unknown IDs:** an unknown or expired ID does **not** return 404. It silently starts a new
     session, so always adopt the returned ID.
3. **Clarifications:** when the LLM needs more information, its question simply arrives as `answer`,
   with `llm_generated_query: ""` and `sparql_query_result: null`. Reply on the same session.
4. **Query results:** `sparql_query_result` is a **string**. Parse it to get standard SPARQL JSON
   (`head.vars`, `results.bindings`).
5. **Reasoning:** `answer` can contain a `<think>…</think>` block (or text before a lone
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

`sparql_query` and `sparql_results` come from the turn's last successful query step and are `null`
when the turn ran no query of its own (also when it only reused an earlier turn's results).

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
