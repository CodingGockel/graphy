# API reference

Base URL: `http://localhost:8000/api/v1`. All schemas below come from
`backend/src/models/schemas.py`. FastAPI also serves interactive, always-up-to-date docs at
**`http://localhost:8000/docs`** (OpenAPI / Swagger UI).

> Errors from upstream services use `ErrorResponse`
> (`{ "status": "error", "error": "...", "detail": "..." }`) with HTTP **502** (invalid upstream
> response) or **503** (dependency unreachable). See [Architecture › Error handling](./architecture.md#error-handling).

---

## Chat

### `POST /chat/`

Process a natural-language question. Creates a session if none is given.

**Request — `ChatRequest`:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | yes | The user's natural-language question. |
| `session_id` | `string (UUID)` \| `null` | no | Conversation id. `null`/omitted → a new session is created and returned. |

**Response — `ChatResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `answer` | `string` | The natural-language answer, or a clarification question. |
| `session_id` | `string (UUID)` | The session this conversation lives in. **Store it** for follow-ups. |
| `llm_generated_query` | `string` | The SPARQL query that was run. `""` if none. |
| `sparql_query_result` | `string` \| `null` | Raw SPARQL results as a **JSON string** (parse before use). `null` if no query ran. |
| `raw_results` | `object` \| `null` | Reserved/unused. |

- `200 OK` — answer generated. `503` — LLM or GraphDB unreachable.
- There is **no** `followup_question` field; a clarification arrives through `answer`.

See the [Chat & sessions guide](./frontend_chat_sessions.md) for the full client workflow and the
shape of the parsed `sparql_query_result`.

### `GET /chat/models`

List the model IDs available on the configured LLM API.

**Response — `ModelResponse`:** `{ "models": ["alias-huge", "alias-fast", ...] }`
(`200 OK`; `503` if the LLM API is unreachable.)

### `GET /chat/full_table`

Run a fixed, server-side SPARQL query (no LLM) and return a tabular view. Columns come from
`FULL_TABLE_COLUMNS`, the query from `FULL_TABLE_QUERY_PATH`.

**Query parameter:** `limit` (int ≥ 1, optional) — cap the number of rows.

**Response — `FullTableResponse`:**

```jsonc
{
  "full_table": {
    "columns": ["species", "garden", "city", "..."],
    "rows": [
      { "species": "Achillea millefolium", "year": 2024, "...": null }
    ]
  }
}
```

Numeric cells are coerced to int/float by their SPARQL datatype; missing cells are `null`.
(`200 OK`; `503` if the SPARQL endpoint is unreachable.)

---

## Session

### `GET /session/{session_id}/history`

Return the full chronological history of a session (so a client can rebuild the chat and data
views after a reload).

**Response — `HistoryResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | `string (UUID)` | The session. |
| `messages` | `HistoryMessage[]` | Full chronological message list. |

**`HistoryMessage`:**

| Field | Type | Description |
|-------|------|-------------|
| `role` | `"user"` \| `"assistant"` | Who produced the message. |
| `content` | `string` | The message text / answer. |
| `sparql_query` | `string` \| `null` | Query associated with this message, if any. |
| `sparql_results` | `string` \| `null` | Raw SPARQL results (JSON string), if any. |
| `created_at` | `string (ISO datetime)` \| `null` | Server timestamp (present on read; ignored on upload). |

- `200 OK` — history returned. `404` — no such session.

### `PUT /session/{session_id}/history`

Replace the session's **entire** history with the uploaded messages. Creates the session if it
doesn't exist. Order is preserved; `created_at` is ignored.

**Request — `HistoryUpload`:** `{ "messages": HistoryMessage[] }`
**Response:** the resulting `HistoryResponse` (`200 OK`).

Useful for import/migration; not needed for the normal chat flow.

### `DELETE /session/{session_id}`

Delete the session and all its messages (cascade).

- `204 No Content` — deleted. `404` — no such session.

---

## Health

### `GET /health/`

Aggregated health of the dependencies.

**Response — `HealthResponse`:**

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"ok"` \| `"degraded"` \| `"down"` | Overall status. |
| `error` | `string` \| `null` | Semicolon-separated service errors, or `null`. |
| `services` | `{ [name]: ServiceHealth }` | Per-service health: `sparql_service` (GraphDB), `llm_service` (LLM API). |

**`ServiceHealth`:** `{ "status": "ok|degraded|down", "error": string|null, "additional_attributes": { ... } }`

- `200 OK` — overall status is `ok`.
- `503 Service Unavailable` — at least one service is degraded or down (the body still contains the
  full `HealthResponse`).
