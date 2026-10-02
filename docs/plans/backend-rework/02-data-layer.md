# 02: Data layer: sessions, messages, steps

**Depends on:** 01 · **Area:** backend

## Goal

Replace the schema with the three-table model so a turn can persist every tool step. The HTTP API
does **not** change in this ticket: the existing services are adapted to the new repository, so the
frontend keeps working.

## Schema (`db/models.py`)

```
sessions   id uuid PK · title text NULL · title_is_manual bool default false
           created_at · updated_at
messages   id uuid PK · session_id FK CASCADE · turn int · role (user|assistant)
           content text · thinking text NULL · status (running|complete|aborted|error)
           created_at
steps      id uuid PK · message_id FK CASCADE · ordinal int · kind text · args jsonb
           thinking text NULL · ok bool NULL · count int NULL · result jsonb NULL
           error text NULL · duration_ms int NULL · created_at

UNIQUE messages (session_id, turn, role) · UNIQUE steps (message_id, ordinal)
INDEX  sessions (updated_at DESC)
```

- The two unique constraints replace plain indexes: `next_turn` is a race when two tabs send in
  the same session, and a duplicate turn should fail loudly instead of corrupting the history.
- User messages are always `complete`. `ok`, `count`, `duration_ms` are NULL while a step runs.
- `steps.thinking` is the model's reasoning before that tool call (filled from ticket 11 on);
  `messages.thinking` is the reasoning before the final answer. `count` is the number of rows
  (`sparql_query`, `previous_results`) or candidates (`resolve_entity`), NULL otherwise.
- `title_is_manual` is what "a manually set title is never overwritten" (ticket 09) hangs on.

## Repository (`db/repository.py`)

Recut `ChatRepository`:

- sessions: `create_session`, `session_exists`, `get_sessions(ids)`, `set_title(id, title, manual)`,
  `touch_session` (bumps `updated_at`), `delete_session`
- messages: `add_message(session_id, turn, role, content, status)`,
  `finish_message(id, content, thinking, status)`, `next_turn(session_id)`
- steps: `start_step(message_id, ordinal, kind, args, thinking=None)`,
  `finish_step(id, ok, count, result, error, duration_ms)`, `get_step_result(id)`
- reads: `get_history(session_id, turns)` returns the last N **complete** turns with their steps;
  `get_full_history(session_id)` returns everything. Neither loads `steps.result`: a result is
  fetched with `get_step_result` only when it is actually needed.

Removed: `save_message`, `ensure_session`, `replace_history`.

Every repository method ends its transaction, reads included. From ticket 05 on a DB session
lives as long as the stream; a read that leaves its transaction open would pin a pooled
connection ("idle in transaction") through every LLM call.

## Adapting the existing callers (temporary, replaced in 04 and 07)

- `ChatService.process()`: writes the user message, creates the assistant message, writes **one**
  step for the last executed query (as today, only the last query survives), finishes the message.
  `_build_history` builds the turn map from steps instead of `Message.sparql_query`: keyed on
  `messages.turn` (today the turns are counted inside the loaded window, so the numbers shift
  once the history depth is exceeded), holding the step ID and query of the turn's last
  successful `sparql_query` step. The result is loaded via `get_step_result` when
  `use_previous_results` is called.
- `SessionService.get_history()`: keeps the `HistoryResponse` shape and fills `sparql_query` /
  `sparql_results` from the turn's last successful `sparql_query` step (result via
  `get_step_result`).
- `PUT /session/{id}/history` and `HistoryUpload` are **removed** now (the frontend does not use
  them, and `replace_history` has no sensible meaning with steps).

## Migration

None. `create_all` does not alter existing tables: `cd database && docker compose down -v`, then
`up -d`.

## Tests

- `tests/factories.py`: `make_db_message` gets `turn`, `status`, `steps`; new `make_db_step`.
- Adapt `test_chat_service.py`, `test_session_service.py`, `test_session_router.py` (drop the PUT
  tests). New `tests/test_db/test_repository.py` against a mocked `AsyncSession` for the
  history query shape (only complete turns, turn ordering, no `result` loaded).

## Docs

- `docs/api.md`: remove `PUT /session/{id}/history`.
- `docs/architecture.md`: data model section.
- `docs/setup.md`: note that the DB volume must be recreated.
