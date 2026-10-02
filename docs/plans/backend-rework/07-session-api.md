# 07: Session API

**Depends on:** 02 (independent of 05) · **Area:** backend · **lands together with 08**

## Goal

The final session endpoints. The session list stays client-side; the backend serves metadata for
the IDs a client already knows.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/sessions?ids=a,b,c` | Metadata for the given IDs: `id`, `title`, `updated_at`, `message_count`. Unknown IDs are omitted. `ids` is required, max 100. |
| `GET` | `/sessions/{id}` | Full history: messages (`id`, `turn`, `role`, `content`, `thinking`, `status`, `created_at`) with their steps (`id`, `ordinal`, `kind`, `args`, `thinking`, `ok`, `count`, `error`, `duration_ms`; no `result`). 404 if unknown. |
| `PATCH` | `/sessions/{id}` | `{ "title": "…" }`; sets `title_is_manual`. 404 if unknown. |
| `DELETE` | `/sessions/{id}` | 204 / 404. |
| `GET` | `/steps/{id}/result` | `{ "step_id", "kind", "result" }`; 404 if unknown. |
| `GET` | `/table` | was `/chat/full_table` |
| `GET` | `/models` | was `/chat/models` |

There is deliberately **no** endpoint that lists all sessions (no auth; see README, refinement 2).

## Changes

- `api/v1/session.py` → `api/v1/sessions.py` (prefix `/sessions`, plus the `/steps` route);
  `session_service.py` rewritten on the repository from 02.
- `models/schemas.py`: `SessionSummary`, `SessionDetail`, `MessageOut`, `StepOut`,
  `SessionRename`, `StepResult`; remove `HistoryMessage`, `HistoryResponse`.
- A message still `running` is returned as `aborted` unless it is younger than
  `RUNNING_STALE_AFTER` (constant in `session_service.py`, 10 minutes): a turn may really be in
  progress in another tab.
- `/table` and `/models` move out of the chat router into their own small router; behaviour
  unchanged.
- `main.py`: router registration.

## Tests

- Rewrite `test_session_service.py` and `test_session_router.py`: ids filter and cap, omitted
  unknown IDs, detail without step results, rename sets the manual flag, delete, step result 404, stale `running` reported as `aborted`.
- `test_chat_router.py`: move the models / table tests to the new paths.

## Docs

- `docs/api.md`: sessions section rewritten; path changes.
- `CLAUDE.md`: router list.
