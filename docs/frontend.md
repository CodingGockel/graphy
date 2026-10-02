# Frontend

The Vue app in `frontend/`. It is a generic UI for SPARQL agents, so nothing specific to one
knowledge graph belongs here: no maps, no predefined tables, no KG-specific example questions.

## Scope

- **Chat** with the agent.
- **Session sidebar:** new session, add an existing session by ID, switch, rename, delete.
- **Settings:** language and theme.
- **Service status** of the backend, knowledge graph and LLM.

Query/result display, model selection and similar features come later, together with the backend
changes in [plans/streaming-rework.md](./plans/streaming-rework.md).

## Stack and rules

- Vue 3 (`<script setup>`, TypeScript) + Vite.
- **As few dependencies as possible.**
  - Runtime: `vue`, `marked`, `dompurify`.
  - Dev: `vite`, `@vitejs/plugin-vue`, `typescript`, `vue-tsc`.
- No Tailwind, no UI library, no state library, no router (add `vue-router` once there is more than
  one page).
- Plain CSS: design tokens in `src/styles/base.css`, component styles scoped.
- Backend calls only go through `src/api/client.ts`. `src/api/types.ts` mirrors
  `backend/src/models/schemas.py` and the chat events in `backend/src/models/events.py`.
  - **Chat is a stream:** `api.chat(message, sessionId, onEvent, signal)` reads the SSE response
    of `POST /chat` with `fetch` + `ReadableStream` (`EventSource` cannot `POST`) and a small
    parser in `client.ts`; no dependency. It calls `onEvent` per event and rejects with
    `ApiError` on an HTTP error or when the stream ends without `done` / `error`.
  - **`state/chat.ts`** adopts the session from the `session` event, appends `answer` deltas to
    the assistant entry and turns an `error` event into the same error box (with retry) as an
    HTTP error (`lib/errors.ts` maps its `kind`). `session_title` sets the title of the local
    session entry. Steps and reasoning events are ignored for now.
    "Stop" aborts the fetch; a partial answer stays visible. A `404` on send or when opening a
    session removes the stale session from the local list; the error box then offers "New
    session" instead of a retry, which could not succeed.

## Structure

```
frontend/
  index.html            favicons, manifest, theme applied before first paint
  public/               favicon.svg/.ico, apple-touch-icon, icon-192/512, site.webmanifest
  src/
    api/                client.ts (fetch wrapper, SSE reader, ApiError), types.ts
    components/         AppSidebar, SessionItem, StatusPanel, ChatView, ChatMessage, ChatInput,
                        GraphLoader, BaseDialog, SettingsDialog, AddSessionDialog,
                        AppLogo, AppWordmark, AppIcon
    i18n/ + locales/    t() helper; de.json, en.json, fr.json
    lib/                storage (safe localStorage), markdown, thinking (<think> splitter), errors
    state/              settings, sessions, chat, health (plain reactive modules)
    styles/base.css     tokens, light/dark, shared controls, scrollbars
```

## Design

- **Look:** modern but calm, explicitly not the typical "AI landing page": no gradients, no glow, no
  decorative effects.
- **Shapes:** moderate rounding via tokens:
  - `--radius-sm` 6px for controls
  - `--radius` 10px for panels
  - `--radius-lg` 14px for bubbles, the input and dialogs
- **Borders and shadows:** 1px borders. Shadows only faint (`--shadow-sm`) or on floating layers
  (dialog, mobile drawer).
- **Color:** neutral greys, with blue as a subtle accent (`--accent`: links, focus ring, send button,
  active session).
- **Brand:** the logo blue is `--brand` (`#1570ef`), the same in both themes.
- **Theme:** follows the system by default; switchable in the settings (`system` / `light` / `dark`).
- **Motion:** only short transitions (≤150 ms). The global `prefers-reduced-motion` rule turns them
  off.
- **Scrolling:** the page itself never scrolls, only the chat and the session list. Scrollbars are
  thin and have no track.

## Layout

- **Desktop:** a fixed left sidebar, like ChatGPT, Claude or Langdock:
  1. Graphy wordmark
  2. **New session** and **Add session**
  3. the session list
  4. service status and **Settings** at the bottom

  The chat fills the rest, in a centered column.
- **Mobile (< 768px):** a top bar with the wordmark, a status dot and the menu button on the
  **right** (thumb reach). The sidebar slides in as a drawer from the right and closes on selection,
  backdrop click or Esc.

## Chat

- **Bubbles:**
  - user messages on the right, tinted light blue
  - answers on the left, bordered, with the Graphy icon as avatar
  - the corner facing the speaker is flattened like a speech-bubble tail
- **Answers:** rendered as Markdown (`marked`) and sanitized with `DOMPurify`. Links open in a new
  tab.
- **Reasoning:** `<think>…</think>` (or text before a lone `</think>`) is split off by
  `lib/thinking.ts`. It appears as a collapsed "Reasoning" section at the top of the bubble.
- **Waiting:** `GraphLoader` shows a breadth-first traversal of a small graph. Tree edges draw from
  node to node and the reached nodes light up. A timer drives the steps, so it also runs under
  reduced motion, just without the soft transitions.
- **Stop button:** aborts the request in the browser. The backend stops the turn and stores it as
  aborted.
- **Input:** an auto-growing textarea. Enter sends, Shift+Enter inserts a newline.
- **Errors:** shown inline, with a localized headline, collapsible backend details and "Try again".

## Sessions

Which sessions belong to a browser is kept in `localStorage` (`state/sessions.ts`):
`{ id, title, updatedAt }` per session, plus the active ID. The backend has no authentication, so
a list of all sessions would show every visitor every chat; it only serves metadata for IDs the
client already knows.

- **On start:** `refreshSessions()` asks `GET /sessions?ids=…` (in chunks of 100) for the stored
  IDs and takes over titles and `updatedAt`. Sessions the backend no longer knows are dropped
  from the list. If the request fails (backend down), the list stays as it is.
- **New session:** the `session` event of the first turn carries the `session_id`, and the session
  is added to the list with the shortened first question as its title. That local title stays
  until the backend's title arrives in the `session_title` event of the same turn.
- **Add session:** you enter an ID; it is validated with `GET /sessions/{id}`.
- **Open:** loads the history with `GET /sessions/{id}`. The last active session reopens after a
  reload.
  - A turn that failed without any answer text is skipped as a pair (question and answer): after
    "Try again" the same question would otherwise appear twice.
  - An aborted turn keeps its question; an answer without text is not rendered as an empty bubble.
- **Per session:**
  - copy ID
  - rename (`PATCH /sessions/{id}`, then the local entry)
  - delete (`DELETE /sessions/{id}`, after confirmation)

## Service status

`state/health.ts` polls `GET /health` every 60 s while the tab is visible, and again when the tab
regains focus (at most every 15 s). A `503` from `/health` is read as a normal status body.

`StatusPanel` shows an overall dot with a summary and can be expanded to show each service.

## Localization

- **Languages:** German, English and French, in `src/locales/{de,en,fr}.json`.
- **Usage:** templates use `t('section.key')`. `{name}` placeholders are filled from parameters.
- **Loading:** only the selected locale is loaded. The default is the browser language, falling back
  to English. `<html lang>` follows the setting.
- **New strings:** every new UI string needs a key in **all three** files.

## Branding

- **Sources:** `docs/designs/graphy-icon.svg` and `graphy-wordmark.svg`. Both were vectorized from
  the PNG drafts in `docs/designs/drafts/` and have transparent backgrounds.
- **In the app:**
  - `AppLogo.vue`: the icon.
  - `AppWordmark.vue`: icon plus lettering. The lettering uses `currentColor`, so it follows the
    theme.
- **Favicons** (`frontend/public/`):
  - `favicon.svg`, `favicon.ico` (16/32/48)
  - `apple-touch-icon.png`: 180 px on a white background without alpha, because iOS renders
    transparency black.
  - `icon-192.png` and `icon-512.png` for `site.webmanifest`.
