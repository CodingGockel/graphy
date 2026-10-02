# 06: Frontend: SSE client

**Depends on:** 05 · **Area:** frontend · **lands together with 05**

## Goal

The frontend talks to the streaming `POST /chat`. Same UI as today; the answer simply arrives
through the stream. No new dependency.

## Changes

- `api/types.ts`: event types mirroring `backend/src/models/events.py`; remove `ChatResponse`.
- `api/client.ts`: `api.chat(message, sessionId, onEvent, signal)` using `fetch` + `ReadableStream`
  (`EventSource` cannot POST). A small SSE parser: split on blank lines, read `event:` / `data:`,
  ignore comment lines (`: ping`), tolerate frames split across chunks. A non-2xx response is
  turned into `ApiError` as today. The stream ending without `done` or `error` is an `ApiError`.
- `state/chat.ts`, `send()`:
  - `session` → adopt `session_id` (`touchSession`, `activeId`).
  - `answer` → append `delta` to the assistant entry (created on the first delta).
  - `error` → `chatError` with retry, as today for HTTP errors. Map `kind` to the existing error
    texts in `lib/errors.ts`.
  - `done` → finished. `step_*`, `thinking`, `session_title` are ignored for now.
  - `stop()` still aborts the fetch; a partial answer stays visible.
- A 404 on send (session unknown to the backend) drops the stale ID from the local list and shows
  the error.

## Out of scope

- Step display and live reasoning: ticket 12.

## Tests

- No frontend test setup exists; verification is `npm run check` and a manual run.

## Docs

- `docs/frontend.md`: API layer section.
- New i18n strings (if any) in `de.json`, `en.json`, `fr.json`.
