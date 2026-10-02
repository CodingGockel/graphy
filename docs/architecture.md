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
| `api/v1/` | Routers: `chat` (the SSE stream), `sessions` (sessions and step results), `info` (`/models`, `/table`), `health`. |
| `api/dependencies.py` | Dependency injection: builds the services from `app.state`. |
| `api/exception_handlers.py` | Maps domain exceptions to HTTP 404 / 502 / 503, and to the `error` event of a chat stream. |
| `services/chat_service.py` | The tool loop as an event generator (`run()`), persisting each turn step by step. |
| `services/llm_service.py` | Wraps the OpenAI client: tool-calling turns and the final answer call. |
| `services/sparql_service.py` | Runs SPARQL over HTTP against GraphDB. |
| `services/lucene_service.py` | Entity lookup in the Lucene index (`resolve_entity`). |
| `services/session_service.py` | Session metadata, history, rename, delete; step results. |
| `services/build_prompt.py`, `lucene_setup.py` | Standalone CLIs to build the prompts and the Lucene index (see [Knowledge graph](./knowledge-graph.md)). |
| `db/` | Async SQLAlchemy: `models.py` (`ChatSession`, `Message`, `Step`), `repository.py`, `database.py`. |
| `resources/` | Prompts and templates, tool definitions, schema queries, Lucene connector, fixed queries. |

## A chat request

`POST /api/v1/chat` with `{ message, session_id }`:

1. **Session:** without a `session_id` a new session is created. An unknown ID is a `404`, and
   nothing is written. This is checked before the response starts; from then on the status is
   `200` and the response is an event stream.
2. **History:** the last `CHAT_HISTORY_DEPTH` complete turns are loaded from PostgreSQL.
3. **Messages:** the user message is stored, and the assistant message is created with status
   `running`, both in one transaction.
4. **Tool loop:** the LLM works on the question (below). Every tool call is stored as a step when
   it starts and updated when it finishes.
5. **Answer:** the answer is stored, the message set to `complete` and the session's
   `updated_at` bumped, in one transaction.

Each of these steps reaches the client as an event while it happens.

### Events

`ChatService.run()` does not return a response. It is an async generator that yields the events of
the turn (`backend/src/models/events.py`) at the moment they happen:

`session` → (`step_started` → `step_finished`)\* → `answer` → `done`

- **`session`** carries the session ID and the ID of the assistant message.
- **`step_started` / `step_finished`** frame one tool call: its `kind` and arguments, then whether
  it worked, a `count` (rows or candidates) and, for a failed step, the `error` text. Results are
  never part of an event; they are stored in `steps.result`.
- **`answer`** is the answer text, for now as a single event.
- **`done`** ends a complete turn.

The repository is passed to `run()` per turn instead of being held by the service, because its DB
session has to live as long as the event stream.

### The stream

The route (`api/v1/chat.py`) forwards these events as Server-Sent Events
(format: [API](./api.md#post-chat)):

- **Producer and queue:** a task runs `ChatService.run()` and puts the events on a queue; the
  response body reads from it. The task opens its own DB session, which lives as long as the turn
  (a request-scoped session would be closed before the body is sent).
- **Heartbeat:** when the queue stays empty for 15 s, the body sends a `: ping` comment line, so
  proxies don't close an idle stream during a long LLM call.
- **Errors:** an exception in the turn becomes an `error` event (the mapping sits next to the
  HTTP handlers in `api/exception_handlers.py`); the status code is already sent by then.
- **Abort:** when the client disconnects, the response body ends and cancels the producer. The
  producer then marks the assistant message `aborted`, with the answer produced so far, through
  a fresh DB session and shielded from the cancellation. Steps that already ran are kept; a step
  that was running stays without a result.

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

Each tool call becomes a step of the kind `resolve_entity`, `sparql_query`, `previous_results`,
`papers` or `clarification`. A call to a tool that doesn't exist is treated as a clarification.

**How the loop ends:**

- **The LLM stops calling tools.** If it ran queries, a separate `generate_answer()` call writes the
  final answer from the collected data, using the answer prompt. If it never queried, its own text
  is the answer.
- **The iteration limit is reached.** `generate_answer()` forces an answer from whatever data exists.
- **The LLM calls `ask_clarification`.** Its question is returned as the normal `answer`; there is
  no separate flag.
- **`use_previous_results` finds no data.** The step fails and a fixed text is the answer.

**Errors inside the loop:**

- **Bad query** (GraphDB answers HTTP 400 → `SparqlQueryException`): the error text goes back to the
  LLM as the tool result, so it can fix the query and retry.
- **No Lucene connector** (`resolve_entity` fails with a `SparqlQueryException`): the step fails and
  the LLM is told to match labels with a query instead.
- **Infrastructure errors** (`SparqlDatabaseException`, `SparqlDatabaseStatusCode`): these abort the
  turn; the client gets an `error` event.
- **Any exception** that aborts the turn (a bug included) sets the assistant message to `error`
  first; the step that was running is closed as failed, earlier steps stay as they are. The
  step's error text is the exception message only for a domain exception, otherwise a generic
  "Internal server error". A message that was already stored as `complete` is not changed.

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
  always `complete`. Only complete turns are sent to the LLM as history, with any `<think>`
  reasoning removed from the answers.
- **Steps:** `kind` is `resolve_entity`, `sparql_query`, `previous_results`, `papers` or
  `clarification`; `(message_id, ordinal)` is unique. `count` is the number of rows or candidates.
  `result` holds the full result (for a query: the SPARQL JSON) and is never loaded together with
  the history, only on demand by step ID.
- **Reusing data:** `use_previous_results` refers to a turn by its `turn` number and gets the result
  of that turn's last successful `sparql_query` step. A turn that itself only reused data passes
  that data on: its `previous_results` step points at the step holding the result.
- **Transactions:** every `ChatRepository` method ends its transaction, reads included.

A `previous_results` step stores no `result` of its own (it would duplicate the referenced step);
its `args` name the turn it resolved to (`reference_turn`) plus the step that holds the data
(`source_step_id`) and its `query`. A `papers` or `clarification` step has no result either.

Because history lives on the server, a client only has to remember the `session_id`.

## Errors

The API maps domain exceptions to status codes and returns
`{ "status": "error", "error": "...", "detail": "..." }`:

- **404** — unknown session or step.
- **502** — an upstream service answered with an error (bad SPARQL status, empty LLM output).
- **503** — the LLM API or GraphDB is unreachable.

## What's next

The planned move to a streamed response (SSE): live steps, thinking and answer tokens, a session
list, LLM-generated titles. See [plans/streaming-rework.md](./plans/streaming-rework.md).
