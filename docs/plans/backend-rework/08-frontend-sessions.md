# 08: Frontend: session endpoints

**Depends on:** 07 · **Area:** frontend · **lands together with 07**

## Goal

Bind the new session endpoints. The list of known IDs stays in `localStorage`.

## Changes

- `api/types.ts`: `SessionSummary`, `SessionDetail`, `MessageOut`, `StepOut`; remove
  `HistoryMessage`, `HistoryResponse`.
- `api/client.ts`: `getSessions(ids)`, `getSession(id)`, `renameSession(id, title)`,
  `deleteSession(id)` on `/sessions`; remove `getHistory`.
- `state/sessions.ts`: on start, refresh titles and `updatedAt` for the stored IDs via
  `getSessions` (in chunks of 100, the backend's limit); IDs the backend no longer knows are dropped from the list. A failed refresh
  (backend down) keeps the local list untouched. Renaming goes through `PATCH` and then updates
  the local entry.
- `state/chat.ts`: `openSession` / `importSession` use `getSession`. A turn whose assistant
  message has status `error` and no content is skipped as a pair (question and answer): after a
  retry the same question would otherwise appear twice. An aborted turn keeps its question; its
  answer is not rendered as an empty bubble.
- The local `makeTitle` stays as the title until the backend has one (ticket 09).

## Out of scope

- Showing steps (ticket 12) or a per-message status marker.

## Docs

- `docs/frontend.md`: the sessions section (the "no list endpoint yet" note is replaced by the
  reason the list is client-side).
- `CLAUDE.md`: `state/sessions.ts` description.
