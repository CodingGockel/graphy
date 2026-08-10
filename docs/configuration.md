# Configuration

All backend configuration comes from `backend/.env`, loaded once at startup by
`backend/src/util/config.py` (`get_settings()`). **Settings are read-only at runtime** — there is no
settings API; to change a value, edit `.env` and restart the backend. Copy the template to start:

```bash
cd backend
cp .env.example .env
```

## Backend settings (`backend/.env`)

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `BLABLADOR_API_KEY` | yes | `sk-...` | API key for the Blablador (OpenAI-compatible) LLM API. |
| `BLABLADOR_BASE_URL` | yes | `https://api.helmholtz-blablador.fz-juelich.de/v1/` | Base URL of the LLM API. |
| `BLABLADOR_SPARQL_MODEL` | yes | `alias-huge` | Model used for the whole tool-calling loop and the final answer. |
| `GRAPHDB_BASE_URL` | yes | `http://graphdb-lehre.inf-bb.uni-jena.de:32833` | GraphDB server base URL. |
| `GRAPHDB_REPOSITORY` | yes | `SWEPLARGE` | GraphDB repository id. The SPARQL endpoint is `{GRAPHDB_BASE_URL}/repositories/{GRAPHDB_REPOSITORY}`. |
| `DATABASE_URL` | yes | `postgresql+asyncpg://admin:admin@localhost:5432/db` | Async SQLAlchemy DSN for PostgreSQL. Must match the `database/.env` credentials. |
| `CHAT_HISTORY_DEPTH` | yes | `3` | Number of prior turns loaded from the DB per request. |
| `CHAT_MAX_TOOL_ITERATIONS` | yes | `5` | Upper bound on the agentic tool loop. |
| `SYSTEM_PROMPT_PATH` | yes | `src/resources/prompts/system_prompt.md` | Path to the generated query system prompt (written by `build_prompt.py`). |
| `ANSWER_SYSTEM_PROMPT_PATH` | no | `src/resources/prompts/answer_system_prompt.md` | Path to the generated answer system prompt (written by `build_prompt.py`). |
| `FULL_TABLE_QUERY_PATH` | no | `src/resources/queries/full_table.rq` | SPARQL query backing `GET /chat/full_table`. |
| `FULL_TABLE_COLUMNS` | no | `["species","garden","city",...]` | JSON array of column names for the full-table view. |

Notes:
- `DATABASE_URL` uses the `postgresql+asyncpg://` driver. The default credentials
  (`admin:admin@localhost:5432/db`) line up with the `database/.env.example` defaults.
- `FULL_TABLE_COLUMNS` is a JSON list; keep it on one line in `.env`.
- The two system prompts are **generated** by `build_prompt.py` from templates. The inputs to that
  composer — `GENERIC_RULES_PATH`, `KG_PROFILE_PATH`, `GENERIC_ANSWER_PATH`, `KG_ANSWER_PROFILE_PATH`
  and `SCHEMA_PREFIXES_PATH` — all have defaults in `config.py` and normally don't need to be set in
  `.env`. See [Onboarding a new KG](./onboarding-new-kg.md).

## Database settings (`database/.env`)

The PostgreSQL container reads `database/.env` (see [Database setup](./database_setup.md)). Copy
`database/.env.example`:

| Variable | Example | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `admin` | Database user created on first run. |
| `POSTGRES_PASSWORD` | `admin` | Password for that user. |
| `POSTGRES_DB` | `db` | Database name created on first run. |
| `POSTGRES_PORT` | `5432` | Host port mapped to the container's `5432`. |

These must stay consistent with the backend `DATABASE_URL`. With the defaults above, the matching
DSN is `postgresql+asyncpg://admin:admin@localhost:5432/db`.

## Frontend

The frontend has no `.env`; its backend URL is currently hard-coded to `http://localhost:8000/api/v1`.
User preferences (theme, CSV separator, etc.) are stored in the browser. See
[Frontend setup](./frontend_setup.md).

## Secrets & git

`.env` files contain secrets (the Blablador key, DB password) and are git-ignored. Only the
`.env.example` templates are committed. Never commit a real `.env`.
