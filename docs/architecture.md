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
| `api/v1/` | Routers: `chat` (the SSE stream), `sessions` (sessions and step results), `info` (`/models`), `health`. |
| `api/dependencies.py` | Dependency injection: builds the services from `app.state`. |
| `api/exception_handlers.py` | Maps domain exceptions to HTTP 404 / 502 / 503, and to the `error` event of a chat stream. |
| `services/chat_service.py` | The tool loop as an event generator (`run()`), persisting each turn step by step. |
| `services/llm_service.py` | Wraps the OpenAI client: tool-calling turns and the final answer call. |
| `services/sparql_service.py` | Runs SPARQL over HTTP against GraphDB. |
| `services/lucene_service.py` | Entity lookup in the Lucene index (`resolve_entity`). |
| `services/session_service.py` | Session metadata, history, rename, delete; step results. |
| `services/build_prompt.py`, `lucene_setup.py` | Standalone CLIs to build the prompts and the Lucene index (see [Knowledge graph](./knowledge-graph.md)). |
| `db/` | Async SQLAlchemy: `models.py` (`ChatSession`, `Message`, `Step`), `repository.py`, `database.py`. |
| `resources/` | Prompts and templates, tool definitions, schema queries, Lucene connector. |

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

`session` → (`step_started` → `step_finished`)\* → `answer`+ → `done`, with `thinking` before a
step or the answer

- **`session`** carries the session ID and the ID of the assistant message.
- **`session_title`** carries the title of a session that had none. `LLMService.generate_title()`
  runs as a task next to the turn, so it never delays the stream; the title is stored and sent
  between two loop iterations once it is there, at the latest before `done` (then waited for up
  to `SESSION_TITLE_TIMEOUT`). A failed or slow call falls back to the shortened question and
  never fails the turn; a title set by hand is never overwritten.
- **`step_started` / `step_finished`** frame one tool call: its `kind` and arguments, then whether
  it worked, a `count` (rows or candidates) and, for a failed step, the `error` text. Results are
  never part of an event; they are stored in `steps.result`.
- **`answer`** is the answer text: token by token when it is written from query results,
  otherwise in one event.
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

The LLM is called at most `CHAT_MAX_TOOL_ITERATIONS` times. Each reply is one or several tool calls
(e.g. one `resolve_entity` per name the user mentioned); they are executed in order. With
`LLM_TOOL_CHOICE=required` (the default) a reply is always a tool call. Tool definitions are JSON
files in `backend/src/resources/llm_tools/`.

| Tool | What it does |
|------|--------------|
| `resolve_entity` | Looks up a name (species, place, …) in the Lucene index and returns candidate URIs, so the LLM doesn't guess them. |
| `execute_sparql_query` | Runs a SPARQL query and feeds the results back. |
| `use_previous_results` | Reuses the results of an earlier turn (`reference_turn`) instead of querying again. |
| `ask_clarification` | Returns a question to the user and ends the loop. |
| `finish` | Ends the loop: enough data is collected, or the message needs none (a greeting). |

Each tool call becomes a step of the kind `resolve_entity`, `sparql_query`, `previous_results`
or `clarification`; `finish` is not a step. A call to a tool that doesn't exist is treated as a
clarification.

The prompt tells the model to **resolve first**: every name the user mentions goes through
`resolve_entity`, and the query then uses the returned URI instead of matching a label as text
(labels may be in another language than the question).

**Context:** within a turn everything shares one context. The loop transcript grows with every
tool call and its result (a large result is cut to a sample there). The answer call gets the
earlier questions and answers of the chat, the question, the resolved entities and **every**
successful query of the turn with its result (the last result in full, earlier ones as the same
sample). Across turns only question and answer are kept as history, plus the list of turns whose
data `use_previous_results` can reuse.

**How the loop ends:**

- **The LLM calls `finish`.** A separate `generate_answer_stream()` call writes the final answer
  from the collected data, using the answer prompt; it is streamed token by token. This is also
  how a message without data (a greeting) is answered. Other tool calls in the same reply are
  still executed.
- **The LLM writes text instead of a tool call** (`LLM_TOOL_CHOICE=auto`, or a server that ignores
  `required`). If it ran queries, the answer call writes the answer as above. If it never queried,
  its own text is the answer, sent in one piece.
- **The iteration limit is reached.** `generate_answer_stream()` forces an answer from whatever
  data exists.
- **The LLM calls `ask_clarification`.** Its question is returned as the normal `answer`; there is
  no separate flag. Tool calls after it in the same reply are not executed.
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

**Streaming:** the rule is *stream for display, parse on the buffer*.

- **Tool loop:** `LLMService.chat_with_tools()` is an async generator. It requests a stream, passes
  on only the reasoning while it is written (`util/think_splitter.py` routes the deltas and holds
  back a tag that is split across two of them) and buffers everything else: text may turn out to
  be a text-encoded tool call or the final answer. With `LLM_TOOL_CHOICE=required` all text of a
  loop call is reasoning (`ReasoningOnlySplitter`: tags removed, cut at a tool-call marker), since
  it cannot be an answer. At the end the complete message is rebuilt
  (tool-call fragments are joined by index) and the tool detection runs on it exactly as it would
  on a non-streamed response. Its last item is the `LLMTurn`. `LLM_STREAM_TOOL_LOOP=false` makes
  the loop calls plain requests, for servers that parse tool calls less reliably when streaming.
- **Answer:** `generate_answer_stream()` yields `(kind, delta)` with the kind `thinking` or
  `answer`; no tool parsing is involved.
- **Storing reasoning:** the reasoning before a tool call is stored with that step
  (`steps.thinking`; with several calls in one reply, with the first); the reasoning after the
  last step (the loop's last call plus the answer
  call) with the message (`messages.thinking`). `PERSIST_THINKING=false` skips both; the events are
  still sent. Reasoning that only ends with a lone `</think>` cannot be recognized while streaming;
  `split_think()` separates it on the complete text before the message is stored.
- **Abort:** a turn that is cancelled mid-answer is stored as `aborted` with the answer text and
  the reasoning written so far.

**Model quirks:**

- **Tool calls as plain text:** some models send tool calls as text (XML, JSON, fenced). `LLMService`
  recovers these.
- **Dropped `</think>`:** Blablador (MiniMax) drops the closing tag in front of a tool call
  (streamed or not) and whenever a request with tools is streamed. The tags then cannot separate
  reasoning from text the model writes to the user. `LLM_TOOL_CHOICE=required` avoids the question:
  the model writes no such text. With `auto`, an answer written without tools sits inside a block
  that never ends; `LLMService` takes the text after the blank-line gap the tag leaves behind as
  the answer, so the turn does not fail, but the live reasoning then contains the answer text too.
- **Reasoning:** `<think>…</think>` blocks (and a separate `reasoning_content` field, if the server
  uses one) are separated from the output and sent as `thinking` events; see Streaming above.

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
- **Steps:** `kind` is `resolve_entity`, `sparql_query`, `previous_results` or
  `clarification`; `(message_id, ordinal)` is unique. `count` is the number of rows or candidates.
  `result` holds the full result (for a query: the SPARQL JSON) and is never loaded together with
  the history, only on demand by step ID.
- **Reusing data:** `use_previous_results` refers to a turn by its `turn` number and gets the result
  of that turn's last successful `sparql_query` step. A turn that itself only reused data passes
  that data on: its `previous_results` step points at the step holding the result.
- **Transactions:** every `ChatRepository` method ends its transaction, reads included.

A `previous_results` step stores no `result` of its own (it would duplicate the referenced step);
its `args` name the turn it resolved to (`reference_turn`) plus the step that holds the data
(`source_step_id`) and its `query`. A `clarification` step has no result either.

Because history lives on the server, a client only has to remember the `session_id`.

## Errors

The API maps domain exceptions to status codes and returns
`{ "status": "error", "error": "...", "detail": "..." }`:

- **404** — unknown session or step.
- **502** — an upstream service answered with an error (bad SPARQL status, empty LLM output).
- **503** — the LLM API or GraphDB is unreachable.

## What's next

The move to a streamed response (SSE) is complete; the plan and its tickets are in
[plans/streaming-rework.md](./plans/streaming-rework.md) and
[plans/backend-rework/](./plans/backend-rework/README.md).
