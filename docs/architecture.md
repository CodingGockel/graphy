# Architecture

DataExplorer turns a natural-language question into a SPARQL query, runs it against a GraphDB
knowledge graph, and answers in natural language. This document explains how the parts fit together
and how a single request flows through the backend.

## Components

| Component | Tech | Responsibility |
|-----------|------|----------------|
| Frontend | SvelteKit 5 | Chat UI, results table, map view. Talks to the backend over HTTP. |
| Backend | FastAPI | Orchestrates the LLM tool loop, runs SPARQL, persists chat history. |
| Knowledge graph | GraphDB | Stores the biodiversity RDF data; answers SPARQL queries. |
| Database | PostgreSQL | Stores sessions and their message history. |
| LLM | Blablador (OpenAI-compatible) | Generates SPARQL and natural-language answers via tool calling. |

## Request flow

For `POST /api/v1/chat`, the layering is **router → service → (LLMService / SparqlService)**:

1. **Router** (`backend/src/api/v1/chat.py`) receives the `ChatRequest` (`message`, optional
   `session_id`) and delegates to `ChatService`.
2. **`ChatService`** (`services/chat_service.py`):
   - Resolves the session (creates a new one if `session_id` is missing or unknown).
   - Loads the last `CHAT_HISTORY_DEPTH` turns of history from PostgreSQL via `ChatRepository`.
   - Runs the **agentic tool-calling loop** (below).
   - Persists the user message and the assistant answer.
   - Returns a `ChatResponse` (`answer`, `session_id`, `llm_generated_query`,
     `sparql_query_result`).
3. **`LLMService`** (`services/llm_service.py`) wraps the Blablador client and drives the tool
   loop. **`SparqlService`** (`services/sparql_service.py`) executes SPARQL against GraphDB.

## The agentic tool loop

Instead of a fixed "generate query → run → answer" pipeline, the LLM drives the process by calling
tools. The loop is bounded by `CHAT_MAX_TOOL_ITERATIONS`. Tool definitions live in
`backend/src/resources/llm_tools/*.json` and are loaded by `util/llm_utils.py:load_tools()`:

| Tool | Purpose |
|------|---------|
| `resolve_entity` | Resolve a name (species, place, …) to real URI(s) via the Lucene full-text index over `rdfs:label`. |
| `execute_sparql_query` | Run a new SPARQL query against GraphDB. |
| `use_previous_results` | Reuse the results of an earlier turn (by `reference_turn`) without re-querying. |
| `ask_clarification` | Return a clarification question to the user; ends the loop. |

Each iteration:

- The model either **calls a tool** or **stops calling tools**. When it stops, the final
  natural-language answer is produced by a separate `LLMService.generate_answer()` call over the
  data collected in the loop (using the answer prompt). If no query was ever run, the model's own
  plain text is used as the answer.
- When it calls `resolve_entity`, the name is looked up in the Lucene index and the candidate URIs
  are fed back; when it calls `execute_sparql_query`, the query is run and the results are fed back —
  in both cases so the model can act on them or query further.
- **Bad-query retry:** if GraphDB rejects a query (HTTP 400 → `SparqlQueryException`), the error
  text is fed back to the model as the tool result, so it can fix the query and try again within
  the same loop. Infrastructure failures (`SparqlDatabaseException` / `SparqlDatabaseStatusCode`)
  are *not* retried — they abort the request.
- If the loop hits `CHAT_MAX_TOOL_ITERATIONS`, `generate_answer()` forces a final answer from
  whatever data was gathered.

Some models don't support structured tool calls; `LLMService` also recovers tool calls that arrive
as text (XML/JSON/markdown-fenced).

> **Clarification** is just the `ask_clarification` tool's question returned through the normal
> `answer` field. There is no separate flag in the response. (The old `followup_question` field and
> the `[RETURN_QUESTION]` token have been removed.)

## Persistence

Sessions and messages are stored in PostgreSQL through an async SQLAlchemy layer in
`backend/src/db/`:

- `models.py` — `Session` and `Message` ORM models.
- `repository.py` — `ChatRepository` (load history, append messages).
- `database.py` — `init_db()` builds the engine + async sessionmaker and **creates tables at
  startup** (called from `main.py`'s lifespan).

Because history lives server-side, a client only needs to remember its `session_id`. See
[Chat & sessions guide](./frontend_chat_sessions.md).

## Configuration & startup

`main.py` (FastAPI `lifespan`) creates the Blablador client and an `httpx` client, calls
`init_db()`, runs a startup **health check**, and registers the routers under `/api/v1`.
Settings come from `backend/.env` via `util/config.py` (`get_settings()`), read once at startup and
**read-only at runtime** (there is no settings API). See [Configuration](./configuration.md).

## Error handling

Domain exceptions are mapped to HTTP status codes in `api/exception_handlers.py`:

- **502 Bad Gateway** — an upstream service returned an invalid response.
- **503 Service Unavailable** — a dependency (LLM API or GraphDB) is unreachable.

Errors use the `ErrorResponse` shape: `{ "status": "error", "error": "...", "detail": "..." }`.
See [API reference](./api_reference.md).

## Other endpoints

Beyond chat, the backend exposes:

- `GET /api/v1/chat/models` — list available LLM models.
- `GET /api/v1/chat/full_table` — a fixed, server-side SPARQL query (no LLM) returning a tabular
  view (columns from `FULL_TABLE_COLUMNS`, query from `FULL_TABLE_QUERY_PATH`).
- `GET/PUT /api/v1/session/{id}/history`, `DELETE /api/v1/session/{id}` — session management.
- `GET /api/v1/health/` — aggregated health of GraphDB + LLM.

## GraphDB & Lucene

SPARQL runs against `{GRAPHDB_BASE_URL}/repositories/{GRAPHDB_REPOSITORY}`. Full-text search uses
GraphDB **Lucene connectors** built from `backend/src/resources/lucene/*.rq` by the standalone
`lucene_setup.py` utility. See [GraphDB & SPARQL](./graphdb_sparql.md).
