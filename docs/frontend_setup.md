# Frontend setup

The frontend is a **SvelteKit 5** app (Svelte runes) in `frontend/`. It provides the chat UI, the
results table, and the map view.

## Prerequisites

- Node.js 20+ and npm.
- A running **backend** at `http://localhost:8000` (the API base URL is currently hard-coded to
  `http://localhost:8000/api/v1`). The backend in turn needs its database and a reachable GraphDB —
  see [Backend setup](./backend_setup.md) and [Database setup](./database_setup.md).

## Install & run

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173
```

Other scripts:

```bash
npm run build        # production build
npm run preview      # preview the production build
npm run check        # svelte-check + TypeScript type checking
```

## How it talks to the backend

- Posts questions to `POST /api/v1/chat` and stores the returned `session_id` to keep conversation
  continuity. See the [Chat & sessions guide](./frontend_chat_sessions.md).
- Loads history via `GET /api/v1/session/{id}/history` and the predefined table via
  `GET /api/v1/chat/full_table`.

## User settings

Frontend-only preferences (e.g. CSV separator, preview height, language, theme) are stored in the
browser via `src/lib/settings.ts` — there is **no settings API** on the backend. (Backend model and
prompt configuration lives in `backend/.env` only.)

## Dependencies

Runtime dependencies are minimal: `leaflet` (map view) and `marked` (markdown rendering). Dev
tooling is SvelteKit + Tailwind + TypeScript (see `frontend/package.json`).
