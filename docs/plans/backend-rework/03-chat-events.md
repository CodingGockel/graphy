# 03: Chat event types

**Depends on:** nothing · **Area:** backend

## Goal

Define the event contract as types. Pure definitions plus the SSE encoder; nothing uses them yet.

## Changes

New `models/events.py`, one Pydantic model per event, each with a literal `event` name, and a
`ChatEvent` union:

| Event | Fields |
|-------|--------|
| `session` | `session_id`, `message_id` (assistant message), `title` (may be null) |
| `session_title` | `session_id`, `title` |
| `step_started` | `step_id`, `ordinal`, `kind`, `args` |
| `step_finished` | `step_id`, `ok`, `count` (nullable), `error` (nullable), `duration_ms` |
| `thinking` | `delta` |
| `answer` | `delta` |
| `done` | `message_id`, `row_count` (nullable) |
| `error` | `kind`, `message` |

- Step `kind`: `resolve_entity`, `sparql_query`, `previous_results`, `papers`, `clarification`.
- Error `kind`: `llm_unavailable`, `llm_no_content`, `sparql_unavailable`, `sparql_failed`,
  `internal`.
- Order of a turn: `session` → (`step_started` → `step_finished`)\* → `answer`+ → `done`.
  `thinking` and `session_title` may appear anywhere after `session`. A `thinking` delta belongs
  to whatever comes next: the following `step_started`, or the answer. `error` ends the stream;
  no `done` follows it.
- `done` has no `status`: it is only sent for a complete turn (an aborted client is gone, a failed
  turn ends with `error`). `error` has no `recoverable` flag: nothing would set or read it, the
  frontend always offers a retry.
- Step results are never part of an event (lazy via `GET /steps/{id}/result`, ticket 07).

`encode_sse(event: ChatEvent) -> str` in the same module: `event: <name>\ndata: <json>\n\n`, the
`event` field itself excluded from `data`. Constant `SSE_PING = ": ping\n\n"`.

## Tests

- New `tests/test_models/test_events.py`: framing of each event, JSON with non-ASCII text on a
  single line, `event` not duplicated inside `data`.

## Docs

- None yet; `docs/api.md` documents the contract in ticket 05, when it becomes reachable.
