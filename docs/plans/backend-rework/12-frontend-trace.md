# 12: Frontend: trace (steps and reasoning)

**Depends on:** 06, 08 · **Area:** frontend

## Goal

The answer bubble shows everything the agent did: every tool call and every reasoning part, in
the order they happened, each as its own collapsible item that looks and behaves like today's
"Reasoning" section. Live while the turn runs, and identical after a reload.

```
▸ Reasoning
▸ Entity lookup · 3 candidates
▸ Reasoning
▸ SPARQL query · failed
▸ SPARQL query · 42 rows
▸ Reasoning
The answer text …
```

This ticket can land before 10 and 11. Until then the backend emits steps but no `thinking`
events, and the trace simply contains steps only.

## State (`state/chat.ts`)

- `ChatEntry` gets `trace: TraceItem[]`:
  - `{ type: 'thinking', text }`
  - `{ type: 'step', id, kind, args, ok: boolean | null, count, error, durationMs }`
    (`ok === null` = still running)
- The assistant entry is created on the `session` event (today: on the first `answer` delta), so
  the trace is visible before the answer starts.
- Live, in `send()`:
  - `thinking` → append `delta` to the last item if it is a thinking item, otherwise push a new one.
  - `step_started` → push a step item. `step_finished` → update it by `step_id`.
- From `getSession` (`openSession` / `importSession`): per message, the steps in `ordinal` order;
  for each step first its `thinking` (if any) as a thinking item, then the step; finally
  `messages.thinking` as the last thinking item. This yields the same list as the live path.
- A step still without `ok` in a message that is not `running` (aborted turn) is shown as
  cancelled.
- An aborted turn without answer text is still rendered if its trace is not empty (ticket 08
  hides only the empty bubble).
- `lib/thinking.ts` stays as a fallback: a `<think>` block still inside `content` becomes the
  last thinking item.

## API (`api/client.ts`, `api/types.ts`)

- `api.getStepResult(id)` → `GET /steps/{id}/result`; type `StepResult`.

## Components

- New `ChatTrace.vue`, rendered at the top of the assistant bubble in `ChatMessage.vue`; the
  `<details>` styling of the current reasoning section moves there and is shared by all items.
  One native `<details>` per item, all collapsed by default (also while streaming), no
  auto-opening.
- Thinking item: label "Reasoning", body as today (muted, pre-wrapped, max height, scrolls).
- Step item, summary line: label by `kind`, then the state: running (muted "…"), `count` with a
  localized unit, or "failed" / "cancelled". No colors beyond the existing muted / text tokens;
  no spinner, no animation besides the chevron.
- Step item, body:
  - `sparql_query`: the query from `args` in a `<pre>`; below it the result.
  - `resolve_entity`: the search term (and type) from `args`; below it the candidates.
  - `previous_results`: the referenced turn from `args`.
  - `papers`, `clarification`: no body, the item is not expandable.
  - failed step: the `error` text instead of a result.
  - unknown `kind`: the kind string as label and `args` as JSON, so new backend tools show up
    without a frontend change.
- Result: fetched with `getStepResult` the first time the item is opened, then kept on the item.
  SPARQL results (`head.vars` / `results.bindings`) render as a plain table of the cell values,
  capped at the first 50 rows with a "50 of N" note; candidates as a list (label, URI). Loading
  and error state inside the body.
- `ChatView.vue`: the `GraphLoader` stays visible while `pending`; the scroll-follow watcher must
  also react to trace changes.

Nothing KG-specific: labels describe the tool kind generically (`papers` → "Documents loaded").

## i18n

All in `de.json`, `en.json`, `fr.json`: one label per step kind, the units (rows, candidates,
with plural), "running", "failed", "cancelled", "query", "result", "N of M rows", result loading
and result error.

## Out of scope

- Remembering which items were open across reloads.
- Exporting or copying results.
- Resuming a running stream after a reload.

## Tests

- No frontend test setup exists; verification is `npm run check` and a manual run (a turn with
  entity lookup, a failed and a corrected query; reload; an aborted turn).

## Docs

- `docs/frontend.md`: the "Reasoning" paragraph in the Chat section becomes the trace; structure
  list gets `ChatTrace`.
- `CLAUDE.md`: components list.
