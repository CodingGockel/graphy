# Architecture

Graphy turns a natural-language question into SPARQL, runs it against a GraphDB knowledge graph and
answers in natural language. The LLM drives this itself by calling tools in a loop.

## Components

| Component | Tech | Responsibility |
|-----------|------|----------------|
| Frontend | Vue 3 + Vite | Chat UI, session sidebar, settings, service status. See [Frontend](./frontend.md). |
| Backend | FastAPI | Runs the LLM tool loop, executes SPARQL, stores chat history. |
| Knowledge graph | GraphDB | Holds the RDF data, answers SPARQL, provides the Lucene full-text index. |
| Database | PostgreSQL | Sessions, their messages and the tool steps of each answer. |
| LLM | Blablador (OpenAI-compatible) | Picks tools, writes SPARQL, writes the answer. |

## Backend layout

Requests flow **router → service → LLMService / SparqlService / LuceneService**.

| Path (`backend/src/`) | Role |
|-----------------------|------|
| `main.py` | App setup (`lifespan`): creates the LLM and HTTP clients, initializes the DB, runs a startup health check, mounts the routers under `/api/v1`. |
| `api/v1/` | Routers: `chat`, `session`, `health`. |
| `api/dependencies.py` | Dependency injection: builds the services from `app.state`. |
| `api/exception_handlers.py` | Maps domain exceptions to HTTP 502 / 503. |
| `services/chat_service.py` | The tool loop and persistence of each turn. |
| `services/llm_service.py` | Wraps the OpenAI client: tool-calling turns and the final answer call. |
| `services/sparql_service.py` | Runs SPARQL over HTTP against GraphDB. |
| `services/lucene_service.py` | Entity lookup in the Lucene index (`resolve_entity`). |
| `services/session_service.py` | Read and delete a session's history. |
| `services/build_prompt.py`, `lucene_setup.py` | Standalone CLIs to build the prompts and the Lucene index (see [Knowledge graph](./knowledge-graph.md)). |
| `db/` | Async SQLAlchemy: `models.py` (`ChatSession`, `Message`, `Step`), `repository.py`, `database.py`. |
| `resources/` | Prompts and templates, tool definitions, schema queries, Lucene connector, fixed queries. |

## A chat request

`POST /api/v1/chat` with `{ message, session_id }`:

1. **Session:** if `session_id` is missing *or unknown*, a new session is created.
2. **History:** the last `CHAT_HISTORY_DEPTH` complete turns are loaded from PostgreSQL.
3. **Tool loop:** the LLM works on the question (below).
4. **Persist:** the user message is stored before the loop, the answer after it, with the last
   executed query and its results as a step.
5. **Response:** `answer`, `session_id`, `llm_generated_query`, `sparql_query_result`.

## The tool loop

The LLM picks one tool per iteration, at most `CHAT_MAX_TOOL_ITERATIONS` times. Tool definitions are
JSON files in `backend/src/resources/llm_tools/`.

| Tool | What it does |
|------|--------------|
| `resolve_entity` | Looks up a name (species, place, …) in the Lucene index and returns candidate URIs, so the LLM doesn't guess them. |
| `execute_sparql_query` | Runs a SPARQL query and feeds the results back. |
| `use_previous_results` | Reuses the results of an earlier turn (`reference_turn`) instead of querying again. |
| `ask_clarification` | Returns a question to the user and ends the loop. |
| `load_phenobs_papers` | PhenObs-specific: loads the first pages of the PhenObs publications (PDFs in `resources/phenobs_papers/`) into context. |

**How the loop ends:**

- **The LLM stops calling tools.** If it ran queries, a separate `generate_answer()` call writes the
  final answer from the collected data, using the answer prompt. If it never queried, its own text
  is the answer.
- **The iteration limit is reached.** `generate_answer()` forces an answer from whatever data exists.
- **The LLM calls `ask_clarification`.** Its question is returned as the normal `answer`; there is
  no separate flag.

**Errors inside the loop:**

- **Bad query** (GraphDB answers HTTP 400 → `SparqlQueryException`): the error text goes back to the
  LLM as the tool result, so it can fix the query and retry.
- **Infrastructure errors** (`SparqlDatabaseException`, `SparqlDatabaseStatusCode`): these abort the
  request.

**Model quirks:**

- **Tool calls as plain text:** some models send tool calls as text (XML, JSON, fenced). `LLMService`
  recovers these.
- **Reasoning in the answer:** `generate_answer()` strips `<think>…</think>` blocks. When the model
  answers directly without any tool, the raw text including `<think>` is returned. The frontend
  splits this off into a collapsible "Reasoning" section.

## Persistence

`init_db()` creates the tables at startup (`Base.metadata.create_all`). It does not alter existing
tables, and there are no migrations yet: after a schema change the database has to be recreated
(see [Setup](./setup.md#1-database)).

| Table | Holds |
|-------|-------|
| `sessions` | `id`, `title` (+ `title_is_manual`), `created_at`, `updated_at`. |
| `messages` | One row per user or assistant message: `session_id`, `turn`, `role`, `content`, `thinking`, `status`, `created_at`. |
| `steps` | One row per tool call of an assistant message: `message_id`, `ordinal`, `kind`, `args`, `thinking`, `ok`, `count`, `result`, `error`, `duration_ms`. |

- **Turns:** a turn is a user message plus the assistant message with the same `turn` number.
  `(session_id, turn, role)` is unique, so two tabs sending into the same session at once fail
  loudly instead of mixing up the history.
- **Status:** an assistant message is `running`, `complete`, `aborted` or `error`; user messages are
  always `complete`. Only complete turns are sent to the LLM as history.
- **Steps:** `kind` is `resolve_entity`, `sparql_query`, `previous_results`, `papers` or
  `clarification`; `(message_id, ordinal)` is unique. `count` is the number of rows or candidates.
  `result` holds the full result (for a query: the SPARQL JSON) and is never loaded together with
  the history, only on demand by step ID.
- **Reusing data:** `use_previous_results` refers to a turn by its `turn` number and gets the result
  of that turn's last successful `sparql_query` step.
- **Transactions:** every `ChatRepository` method ends its transaction, reads included.

For now a turn writes a single step, the last query it executed. Storing every tool call as it
happens comes with the event generator
([ticket 04](./plans/backend-rework/04-chat-service-generator.md)).

Because history lives on the server, a client only has to remember the `session_id`.

## Errors

The API maps domain exceptions to status codes and returns
`{ "status": "error", "error": "...", "detail": "..." }`:

- **502** — an upstream service answered with an error (bad SPARQL status, empty LLM output).
- **503** — the LLM API or GraphDB is unreachable.

## What's next

The planned move to a streamed response (SSE): live steps, thinking and answer tokens, a session
list, LLM-generated titles. See [plans/streaming-rework.md](./plans/streaming-rework.md).
