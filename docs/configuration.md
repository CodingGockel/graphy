# Configuration

Each part reads its own `.env`, except the Docker stack, which uses one root `.env` for everything.
Templates (`.env.example`) are committed; real `.env` files contain secrets and are git-ignored.

| Running | Config file |
|---------|-------------|
| Backend locally | `backend/.env` |
| Database locally | `database/.env` |
| Frontend locally | none needed (optional `VITE_API_BASE_URL`) |
| Full Docker stack | root `.env` (see [Deployment](./deployment.md)) |

Backend settings are loaded once at startup by `backend/src/util/config.py` and are **read-only at
runtime**. To change one, edit `.env` and restart.

## Backend (`backend/.env`)

### LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `BLABLADOR_API_KEY` | required | API key for the Blablador (OpenAI-compatible) API. |
| `BLABLADOR_BASE_URL` | required | e.g. `https://api.helmholtz-blablador.fz-juelich.de/v1/` |
| `BLABLADOR_SPARQL_MODEL` | required | Model for the whole tool loop and the final answer, e.g. `alias-huge`. |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature for all LLM calls. |
| `LLM_MAX_TOKENS` | unset | Optional output-token cap. |
| `LLM_STREAM_TOOL_LOOP` | `true` | Stream the tool-loop calls, so the model's reasoning shows up live. Switch off for a server that handles streamed tool requests badly; the final answer is streamed either way. **Blablador needs `false`:** it drops the closing `</think>` when a request with tools is streamed, so reasoning and answer cannot be told apart. |

### Knowledge graph

| Variable | Default | Description |
|----------|---------|-------------|
| `GRAPHDB_BASE_URL` | required | e.g. `http://graphdb-lehre.inf-bb.uni-jena.de:32833` |
| `GRAPHDB_REPOSITORY` | required | e.g. `SWEPLARGE`. Endpoint: `{BASE_URL}/repositories/{REPOSITORY}` |
| `SPARQL_TIMEOUT` | `30` | Timeout in seconds for SPARQL requests. The health check uses its own fixed 5 s. |

### Chat and persistence

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | required | Async DSN, e.g. `postgresql+asyncpg://admin:admin@localhost:5432/db`. Must match `database/.env`. |
| `CHAT_HISTORY_DEPTH` | required | Number of earlier turns loaded into the LLM context per request. |
| `CHAT_MAX_TOOL_ITERATIONS` | required | Upper bound for the agentic tool loop. |
| `PERSIST_THINKING` | `true` | Store the model's reasoning (`messages.thinking`, `steps.thinking`). Off: it is still streamed, but gone after a reload. |
| `GENERATE_SESSION_TITLES` | `true` | Let the LLM write a session's title from its first question. Off: the shortened question is the title. |
| `SESSION_TITLE_TIMEOUT` | `5` | Seconds a finished turn waits for a title that is still being generated; after that the shortened question is used. |
| `CORS_ALLOW_ORIGINS` | `[]` | JSON list of allowed origins. Not needed locally (Vite proxy) or behind nginx (same origin). |

### Prompts and resources

| Variable | Default | Description |
|----------|---------|-------------|
| `SYSTEM_PROMPT_PATH` | required | Generated query prompt, normally `src/resources/prompts/system_prompt.md`. |
| `ANSWER_SYSTEM_PROMPT_PATH` | `src/resources/prompts/answer_system_prompt.md` | Generated answer prompt. |
| `SESSION_TITLE_PROMPT_PATH` | `src/resources/prompts/title_prompt.md` | Prompt of the title call. Static and KG-agnostic, not generated. |

The inputs of the prompt builder (`GENERIC_RULES_PATH`, `KG_PROFILE_PATH`, `GENERIC_ANSWER_PATH`,
`KG_ANSWER_PROFILE_PATH`, `SCHEMA_PREFIXES_PATH`) have sensible defaults and normally stay unset. See
[Knowledge graph › Onboarding](./knowledge-graph.md#onboarding-a-new-knowledge-graph).

## Database (`database/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `admin` | User created on first start. |
| `POSTGRES_PASSWORD` | `admin` | Its password. |
| `POSTGRES_DB` | `db` | Database created on first start. |
| `POSTGRES_PORT` | `5432` | Host port. |

With these defaults the matching backend DSN is
`postgresql+asyncpg://admin:admin@localhost:5432/db`.

## Frontend

The frontend has no required configuration. It calls the relative path `/api/v1`.

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `/api/v1` | Build-time override for a backend on another origin (then also set `CORS_ALLOW_ORIGINS`). |

User preferences (language, theme) and the local session list are stored in the browser's
`localStorage` under `graphy.*` keys.
