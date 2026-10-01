# Setup (local development)

Three processes run side by side: **PostgreSQL** (Docker), the **backend** (FastAPI) and the
**frontend** (Vite dev server). Start them in this order. The backend needs the database at startup.

## Prerequisites

- Docker with the Compose plugin
- Python 3.12
- Node.js 20.19+ or 22.12+ with npm
- A **Blablador API key**
- Network access to **GraphDB**. The default server (`graphdb-lehre.inf-bb.uni-jena.de`) is only
  reachable over the university VPN.

## 1. Database

```bash
cd database
cp .env.example .env      # defaults: admin / admin / db on port 5432
docker compose up -d
```

This starts a `postgres:16-alpine` container named `db`. Data lives in `database/data/` and survives
restarts. The backend creates its tables itself on startup; there is no migration step.

| Command | Effect |
|---------|--------|
| `docker compose ps` | Status and health |
| `docker compose logs -f` | Follow the logs |
| `docker compose down` | Stop the container (data is kept) |
| `docker compose down`, then delete `database/data/` | Wipe all sessions and history |

## 2. Backend

```bash
cd backend
python -m venv .swep-venv
source .swep-venv/bin/activate       # Windows: .swep-venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # fill in BLABLADOR_API_KEY
uvicorn src.main:app --reload
```

- API: `http://localhost:8000`, interactive docs: `http://localhost:8000/docs`
- Logs: `backend/logs/server.log` (DEBUG) and stdout (INFO)
- On startup the backend checks GraphDB and the LLM API. A failing check shows up in the logs and in
  `GET /api/v1/health`.

All variables are described in [Configuration](./configuration.md).

## 3. Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

The dev server forwards `/api` to `http://localhost:8000` (see `vite.config.ts`), so no CORS setup is
needed.

## Tests and checks

These are run by hand. GitHub has no CI configured yet; `.gitlab-ci.yml` is a leftover from the
GitLab days and only ran the backend tests.

```bash
# backend (from backend/, venv active)
pytest                               # all tests
pytest tests/test_services           # one folder or file
mypy src/                            # type check

# frontend (from frontend/)
npm run check                        # vue-tsc type check
npm run build                        # type check + production build into dist/
```

## Troubleshooting

| Problem | Likely cause |
|---------|--------------|
| Backend fails at startup with a DB error | Postgres not running, or `DATABASE_URL` doesn't match `database/.env` |
| Port 5432 already in use | Change `POSTGRES_PORT` in `database/.env` and the port in `DATABASE_URL` |
| Health shows the SPARQL service `down` | No VPN, or wrong `GRAPHDB_BASE_URL` / `GRAPHDB_REPOSITORY` |
| Health shows the LLM `down` / `degraded` | Wrong `BLABLADOR_API_KEY`, or the configured model is unavailable |
| Frontend says "Backend not reachable" | Backend not running on port 8000 |
