# DataExplorer

DataExplorer is a biodiversity question-answering application. Users ask natural-language
questions about phenological (flowering) observations from botanical gardens; the backend uses an
LLM to generate **SPARQL** queries, runs them against a **GraphDB** knowledge graph, and returns a
natural-language answer together with the underlying data.

- **Frontend:** SvelteKit 5 (Svelte runes) — chat UI, results table, map view.
- **Backend:** FastAPI — an agentic LLM tool-calling loop that generates and runs SPARQL.
- **Knowledge graph:** GraphDB (SPARQL endpoint).
- **Persistence:** PostgreSQL — stores sessions and chat history.
- **LLM:** Blablador (an OpenAI-compatible API).

## Architecture at a glance

```
              ┌────────────┐   POST /api/v1/chat   ┌─────────────────────────┐
   Browser ──▶│  Frontend  │──────────────────────▶│        Backend          │
              │ (SvelteKit)│◀──────────────────────│        (FastAPI)        │
              └────────────┘     answer + data      │                         │
                                                    │  agentic tool loop:     │
                                          ┌─────────│  generate & run SPARQL  │
                                          │         └───────┬─────────┬───────┘
                                          │                 │         │
                                   ┌──────▼──────┐   ┌───────▼───┐ ┌───▼────────┐
                                   │  LLM API    │   │  GraphDB  │ │ PostgreSQL │
                                   │ (Blablador) │   │ (SPARQL)  │ │ (sessions) │
                                   └─────────────┘   └───────────┘ └────────────┘
```

See [`docs/architecture.md`](./docs/architecture.md) for the full request flow and the agentic
tool loop.

## Repository layout

| Path         | What it is |
|--------------|------------|
| `backend/`   | FastAPI backend (`src/`), tests, `requirements.txt`, `.env.example`. |
| `frontend/`  | SvelteKit 5 frontend. |
| `database/`  | PostgreSQL via Docker Compose (sessions + chat history). |
| `docs/`      | Project documentation (start at [`docs/README.md`](./docs/README.md)). |

## Quick start

You need three things running: the **database**, the **backend**, and the **frontend**. A reachable
**GraphDB** endpoint and a **Blablador API key** are also required (configured in `backend/.env`).

```bash
# 1. Database (PostgreSQL via Docker)
cd database
cp .env.example .env          # adjust credentials if you like
docker compose up -d

# 2. Backend (FastAPI)
cd ../backend
python -m venv .swep-venv
source .swep-venv/bin/activate     # Windows: .swep-venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then fill in BLABLADOR_API_KEY (and check GRAPHDB_* / DATABASE_URL)
uvicorn src.main:app --reload # http://localhost:8000  (API docs at /docs)

# 3. Frontend (SvelteKit)
cd ../frontend
npm install
npm run dev                   # http://localhost:5173
```

Per-component instructions:
[backend setup](./docs/backend_setup.md) ·
[database setup](./docs/database_setup.md) ·
[frontend setup](./docs/frontend_setup.md).

## Production / Docker

The whole stack runs from a single root `docker-compose.yml` and one root `.env`. The public
entrypoint is an **nginx** container (`web`) that serves the built static frontend and proxies
`/api` to the backend — so the frontend calls a relative `/api/v1` and there is no hardcoded
backend URL and no CORS in the default setup.

```
                ┌──────────── web (nginx, :WEB_PORT) ───────────┐
   Browser ────▶│  /            → static SPA (built frontend)    │
                │  /api/...     → proxy → backend:8000           │
                └───────────────────────┬───────────────────────┘
                          ┌─────────────┴─────────────┐
                     backend (uvicorn)            postgres
                          │  → GraphDB (external, VPN)
```

```bash
# From the repo root:
cp .env.example .env     # fill in BLABLADOR_API_KEY, change POSTGRES_PASSWORD, etc.
docker compose up -d --build
# open http://localhost:${WEB_PORT}   (default http://localhost)
```

**Important — GraphDB reachability.** The backend talks to an **external** GraphDB
(`GRAPHDB_BASE_URL`) that is gated behind the **university VPN**. The Docker host must have a
network route to it, otherwise chat requests fail (the `/api/v1/health` endpoint will report
`down`/`degraded`). Run the host on the VPN, or arrange equivalent routing.

**One-time prerequisites** (not part of container startup): the generated prompt files
(`backend/src/resources/prompts/system_prompt.md` and `answer_system_prompt.md`) must be present
(committed), and the GraphDB Lucene entity index must already exist. Regenerate them with
`build_prompt.py` / `lucene_setup.py` only when the KG schema changes (both need GraphDB access).

**TLS** is intentionally deferred: the stack serves plain HTTP on `:WEB_PORT`. When the deploy
target is known, either terminate HTTPS in the `web` nginx (a commented `:443` block is in
`frontend/nginx.conf`) or put it behind an upstream proxy/load balancer that handles TLS.

Config is a single root `.env` (template: [`.env.example`](./.env.example)). The per-service
`backend/.env.example` and `database/.env.example` remain for running a component **standalone**
in local dev without Docker.

**Share a public URL (optional).** To expose the running app on a temporary public `https://` URL
without port-forwarding or firewall changes, use the bundled Cloudflare Tunnel:
`docker compose --profile tunnel up -d cloudflared`. See
[docs/cloudflare_tunnel.md](./docs/cloudflare_tunnel.md).

## Documentation

All docs live in [`docs/`](./docs/README.md):

- [Architecture](./docs/architecture.md) — how the pieces fit and the agentic tool loop.
- [Configuration](./docs/configuration.md) — every `.env` variable.
- [Backend setup](./docs/backend_setup.md) · [Database setup](./docs/database_setup.md) · [Frontend setup](./docs/frontend_setup.md)
- [API reference](./docs/api_reference.md) — all HTTP endpoints and schemas.
- [Chat & sessions guide](./docs/frontend_chat_sessions.md) — the session workflow for clients.
- [GraphDB & SPARQL](./docs/graphdb_sparql.md) — endpoint, Lucene connectors, the ad-hoc query skill.
- [Test questions](./docs/backend_test_questions.md) — sample questions for manual testing.

## Team

- **Zoom:** https://uni-jena-de.zoom-x.de/j/2197876598 (passcode: 298772)
- **Discord:** https://discord.gg/pNnfAPnSN
