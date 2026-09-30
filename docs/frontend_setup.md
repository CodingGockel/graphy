# Frontend setup

The frontend (**Graphy**) is a Vue 3 + Vite app in `frontend/`. See
[Frontend requirements](./frontend_requirements.md) for what it does and the design rules.

## Prerequisites

- Node.js 20.19+ or 22.12+ and npm.
- A running **backend** at `http://localhost:8000` (see [Backend setup](./backend_setup.md)).

## Install & run

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173
```

Other scripts:

```bash
npm run check        # vue-tsc type check
npm run build        # type check + production build into dist/
npm run preview      # serve the production build
```

## How it talks to the backend

The app calls the relative path `/api/v1`. In development, Vite proxies `/api` to
`http://localhost:8000` (`vite.config.ts`), so no CORS setup is needed. To point a build at a
different API, set `VITE_API_BASE_URL` at build time.

Endpoints used:

- `POST /api/v1/chat`: send a question (`session_id: null` starts a new session)
- `GET /api/v1/session/{id}/history`: load a session, and validate "Add session"
- `DELETE /api/v1/session/{id}`: delete a session
- `GET /api/v1/health`: service status display; a 503 is read as a normal status body

## Layout

```
frontend/src/
  api/          backend client + mirrored schemas
  components/   Vue components (sidebar, chat, dialogs, icons)
  i18n/         t() helper and locale loading
  locales/      de.json, en.json, fr.json
  lib/          storage, markdown, error helpers
  state/        settings, sessions, chat (plain reactive modules)
  styles/       base.css (design tokens, light/dark, controls)
```
