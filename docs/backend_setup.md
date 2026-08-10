# Backend setup (Python / FastAPI)

The backend is a FastAPI app in `backend/`. These steps get a local dev server running.

## Prerequisites

Before starting the backend, make sure:

- **PostgreSQL is running and reachable** — the backend creates its tables at startup and will fail
  if the DB is down. See [Database setup](./database_setup.md).
- **A GraphDB endpoint is reachable** and configured (`GRAPHDB_BASE_URL` / `GRAPHDB_REPOSITORY`).
- You have a **Blablador API key** for the LLM.

## 1. Create a virtual environment

```bash
cd backend
python -m venv .swep-venv
```

Activate it:

- **macOS / Linux:** `source .swep-venv/bin/activate`
- **Windows:** `.swep-venv\Scripts\activate`

When active, your prompt shows `(.swep-venv)`.

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Configure `.env`

```bash
cp .env.example .env
```

Then fill in `BLABLADOR_API_KEY` and check `GRAPHDB_*` and `DATABASE_URL`. Every variable is
documented in [Configuration](./configuration.md). Settings are read once at startup and are
**read-only at runtime** (there is no settings API).

## 4. Run the dev server

```bash
python uvicorn src.main:app --reload
```

The API is then available at:

- App: `http://localhost:8000`
- Interactive API docs (OpenAPI / Swagger UI): `http://localhost:8000/docs`

At startup the app initializes the database and runs a health check against GraphDB and the LLM API;
check the logs (`backend/logs/server.log`) if something is misconfigured.

## Tests & type checks

The project ships pytest tests and uses mypy. (These are run by you / CI, not automatically.)

```bash
pytest              # run the test suite
pytest tests/path/to/test_file.py   # a single file
mypy src/           # type check
```

CI (`.gitlab-ci.yml`) runs `pytest` for backend changes.

## Project structure

See [Architecture](./architecture.md) for how the backend is organized (routers → services →
LLM/SPARQL, the agentic tool loop, and persistence) and [API reference](./api_reference.md) for the
endpoints.
