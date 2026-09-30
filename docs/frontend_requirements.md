# Frontend requirements (Graphy)

Graphy is a generic web UI for SPARQL agents. It is not tied to a specific knowledge graph: nothing
KG-specific (maps, predefined tables, example questions) belongs in the frontend.

## Scope (v1)

- **Chat** with the agent: question in, natural-language answer out.
- **Session sidebar**: new session, add an existing session by ID, switch, rename, delete.
- **Settings**: language and theme.
- **Service status** in the sidebar: overall dot + summary, expandable per service (backend, knowledge
  graph, LLM) from `GET /health`. It is polled every 60 s while the tab is visible and on refocus
  (at most every 15 s). On mobile the dot also sits in the top bar.

Everything else (query/result display, model selection, …) is out of scope for now and gets
added later as backend features arrive (streaming, session list, steps; see
[`streaming_rework_plan.md`](./streaming_rework_plan.md)).

## Stack

- Vue 3 (`<script setup>`, TypeScript) + Vite.
- As few dependencies as possible. Runtime: `vue`, `marked`, `dompurify`. Dev: `vite`,
  `@vitejs/plugin-vue`, `typescript`, `vue-tsc`.
- No Tailwind, no UI library, no state library, no router (until there is more than one page).
- Plain CSS with custom properties; component styles are scoped.

## Design

- Modern but calm, explicitly **not** the typical AI-landing-page look: no gradients, no glow, no
  decorative effects.
- Moderate rounding via tokens:
  - `--radius-sm` 6px for controls
  - `--radius` 10px for panels
  - `--radius-lg` 14px for bubbles, composer and dialogs
- 1px borders. Shadows only very faint (`--shadow-sm`) or for floating layers (dialog, mobile drawer).
- System font stack; monospace only for IDs/code.
- Neutral greys with **blue as a subtle accent** (links, focus ring, send button, active session, logo).
- Chat messages are **speech bubbles**:
  - user: right-aligned, light accent tint
  - assistant: left-aligned, bordered, with the Graphy mark as avatar
  - the corner facing the speaker is flattened like a bubble tail
- No big animations. Only short transitions (≤150 ms: drawer slide, hover colors), disabled under
  `prefers-reduced-motion`.
- Light and dark mode: follows the system by default, can be switched in the settings
  (`system` / `light` / `dark`).

## Layout

- **Desktop:** fixed left sidebar (like ChatGPT/Claude/Langdock):
  1. "Graphy"
  2. **New session**, **Add session** (enter a session ID)
  3. the session list
  4. **Settings** (gear) at the bottom

  The chat fills the rest, in a centered column.
- **Mobile (< 768px):** a slim top bar with the menu button on the **right** (thumb reach). The
  sidebar slides in as a drawer **from the right**. It closes on selection, on backdrop click or
  with Esc.
- Fully responsive, no horizontal scrolling.

## Chat

- Answers are rendered as Markdown (`marked`), sanitized with `DOMPurify`; links open in a new tab.
- Input is an auto-growing textarea. Enter sends, Shift+Enter inserts a newline.
- While waiting: a plain "thinking" line and a stop button (aborts the request).
- Errors are shown inline as a plain block with a localized headline, collapsible backend details and
  "Try again".

## Sessions

The backend has no endpoint to list sessions yet, so the list is kept in `localStorage`
(`src/state/sessions.ts`). The list stores `{ id, title, updatedAt }` per session, plus the active ID.

- **New session:** the first answer returns the `session_id`, and the session is added to the list.
  Its title is the first question, shortened to about 50 characters.
- **Add session:** you enter an ID. It is checked with `GET /session/{id}/history`; a 404 shows
  "not found".
- **Open:** loads the history from `GET /session/{id}/history`. The last active session is reopened
  after a reload.
- **Per session:**
  - copy the ID
  - rename (local only)
  - delete (`DELETE /session/{id}`, after confirmation)

## Localization

- UI languages: German, English, French. JSON files in `src/locales/{de,en,fr}.json`.
- Templates reference keys via `t('section.key')`. `{name}` placeholders are filled from parameters.
- Only the selected locale is loaded. The default is the browser language, falling back to English.
  `<html lang>` follows the setting.
- A new UI string means one key in **all three** locale files.

## Extending

- A new sidebar feature is a button/section in `AppSidebar.vue`. Once there are several pages, add
  `vue-router`.
- Backend calls live only in `src/api/client.ts`; the schemas mirror
  `backend/src/models/schemas.py` in `src/api/types.ts`.
