# Chat & sessions: client workflow

How a client (the frontend, or any consumer) should drive a conversation with the backend. For the
exhaustive endpoint/schema list, see [API reference](./api_reference.md).

## 1. Mental model

- A **session** is one conversation, identified by a UUID (e.g. `3f1d…-…-9ac2`).
- **The backend owns the chat history.** It stores every user message and assistant answer
  (including the SPARQL query and raw results) for a session. The client only needs to remember the
  `session_id`.
- The assistant runs an **agentic tool loop**: for a given question it may run a new SPARQL query,
  **reuse the results of an earlier turn**, or ask a clarification question. Reusing earlier turns
  only works if you keep sending the **same `session_id`** — otherwise the backend has no history to
  work with.

The single most important rule:

> **Send `session_id` on every message after the first one. Always overwrite your stored
> `session_id` with the one returned in the response.**

---

## 2. The core workflow

```
┌─ New chat ────────────────────────────────────────────────┐
│ 1. POST /chat   { message, session_id: null }              │
│ 2. Response contains session_id  → STORE IT                │
│ 3. POST /chat   { message, session_id: <stored> }   (loop) │
│ 4. Always re-store response.session_id                     │
└────────────────────────────────────────────────────────────┘
```

1. **First message:** `POST /chat` with `session_id: null` (or omit it). The backend creates a new
   session.
2. **Read `session_id` from the response and store it** (e.g. `localStorage`, one id per chat
   thread).
3. **Every following message:** send the stored `session_id`.
4. **Always overwrite** your stored `session_id` with the value from the response (see the
   resilience note).
5. **"New chat":** discard the stored `session_id` and start again from step 1. Optionally call
   `DELETE /session/{id}` to delete the old conversation server-side.

### Resilience note (don't skip this)

If you send a `session_id` the backend doesn't know (expired, wrong, DB reset), the chat endpoint
**does not return 404**. It **silently creates a new session** and returns the new id. That's why
step 4 matters: if you keep posting the stale id you'll keep spawning fresh sessions and lose
continuity. Read `response.session_id` after every call and treat it as the new truth.

---

## 3. Request & response

### `POST /chat` — send a message

**Request body** (`ChatRequest`):

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | `string` | yes | The user's natural-language question. |
| `session_id` | `string (UUID)` \| `null` | no | Conversation id. `null`/omitted → a new session is created. |

**Response body** (`ChatResponse`):

| Field | Type | Description |
|-------|------|-------------|
| `answer` | `string` | The natural-language answer to show in the chat. May also be a **clarification question** (see below). |
| `session_id` | `string (UUID)` | The session this conversation lives in. **Store it** and send it next time. |
| `llm_generated_query` | `string` | The SPARQL query that was run. Empty when no query ran. |
| `sparql_query_result` | `string` \| `null` | Raw SPARQL results as a **JSON string** (see below). `null` when no query ran or on error. |
| `raw_results` | `object` \| `null` | Reserved/unused. |

> **Clarification:** when the assistant needs more information it returns the clarifying question
> as the normal `answer`, with `sparql_query_result: null` and an empty `llm_generated_query`.
> There is **no separate flag** — just render `answer` and wait for the user's next reply on the
> **same `session_id`**. (The old `followup_question` field no longer exists.)

**`sparql_query_result` is a JSON string**, not an object — parse it before use. It has the standard
SPARQL JSON shape:

```jsonc
// JSON.parse(data.sparql_query_result) →
{
  "head":    { "vars": ["species", "count"] },
  "results": { "bindings": [
    { "species": { "value": "Achillea millefolium" }, "count": { "value": "42" } }
  ] }
}
```

---

## 4. Code example

```ts
const API = 'http://localhost:8000/api/v1';

// Read whatever id we stored for this chat thread (null for a brand-new chat).
let sessionId: string | null = localStorage.getItem('sessionId');

async function sendMessage(message: string) {
  const res = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok) {
    // 502/503 → upstream issue; show error and let the user retry.
    throw new Error(`Backend error: ${res.status}`);
  }

  const data = await res.json();

  // ALWAYS adopt the returned id (it may be a freshly created session).
  sessionId = data.session_id;
  localStorage.setItem('sessionId', sessionId);

  // Render the answer (this is also where a clarification question shows up).
  showAssistantMessage(data.answer);

  if (data.sparql_query_result) {
    const parsed = JSON.parse(data.sparql_query_result);
    const columns = parsed.head?.vars ?? [];
    const rows = (parsed.results?.bindings ?? []).map((b: any) =>
      Object.fromEntries(columns.map((c: string) => [c, b[c]?.value ?? ''])),
    );
    renderTable(columns, rows);
  }
}

function startNewChat() {
  sessionId = null;
  localStorage.removeItem('sessionId');
  // (optional) DELETE /session/{old} to clean up server-side.
}
```

### Multi-turn example (including a clarification)

```jsonc
// → POST /chat
{ "message": "How many bee species are recorded?", "session_id": null }
// ← 200
{ "answer": "There are 42 recorded bee species.",
  "session_id": "3f1d…-9ac2",
  "llm_generated_query": "SELECT (COUNT(?s) AS ?count) WHERE { … }",
  "sparql_query_result": "{\"head\":{\"vars\":[\"count\"]}, …}" }

// → POST /chat  (reuse the id!)
{ "message": "And the rarest one?", "session_id": "3f1d…-9ac2" }
// ← 200 — assistant needs clarification; the question is just the answer
{ "answer": "Do you mean fewest observations, or the most narrow range?",
  "session_id": "3f1d…-9ac2",
  "llm_generated_query": "",
  "sparql_query_result": null }

// → POST /chat  (still the same id)
{ "message": "Fewest observations.", "session_id": "3f1d…-9ac2" }
// ← 200 — answered, possibly reusing earlier results internally
{ "answer": "The rarest by observation count is …",
  "session_id": "3f1d…-9ac2",
  "llm_generated_query": "SELECT … ORDER BY ?count LIMIT 1",
  "sparql_query_result": "{\"head\": …}" }
```

---

## 5. Rebuilding a conversation after reload

To restore the full chat (and its data tables) after a page reload, use
`GET /session/{id}/history` as the source of truth rather than a local mirror. It returns every
`HistoryMessage` (`role`, `content`, `sparql_query`, `sparql_results`, `created_at`) in order. See
[API reference › Session](./api_reference.md#session). A `localStorage` cache can stay as an
optimization, but reconcile it with the server history.

---

## 6. Errors

Upstream failures (LLM API or GraphDB unreachable) return `502` or `503` with the `ErrorResponse`
shape:

```json
{ "status": "error", "error": "short message", "detail": "optional details" }
```

Show a friendly error and let the user retry. The session is unaffected.
