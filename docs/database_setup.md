# Database setup (PostgreSQL)

The backend stores sessions and chat history in PostgreSQL. It runs as a Docker Compose service in
the `database/` folder.

## Prerequisites

- Docker and the Compose plugin. Verify with:
  ```bash
  docker --version
  docker compose version
  ```

## Start the database

```bash
cd database
cp .env.example .env      # adjust credentials/port if you like
docker compose up -d
```

This starts a `postgres:16-alpine` container named `db`, mapping `POSTGRES_PORT` (default `5432`) to
the container. Data is persisted in `database/data/` (a bind-mounted volume), so it survives
restarts.

## Configuration

The container reads `database/.env` (see [Configuration](./configuration.md)):

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | `admin` | DB user created on first run. |
| `POSTGRES_PASSWORD` | `admin` | Password for that user. |
| `POSTGRES_DB` | `db` | Database created on first run. |
| `POSTGRES_PORT` | `5432` | Host port mapped to the container. |

These must match the backend's `DATABASE_URL` in `backend/.env`. With the defaults:

```
DATABASE_URL=postgresql+asyncpg://admin:admin@localhost:5432/db
```

## How the backend uses it

On startup, `backend/src/main.py` calls `init_db()` (in `src/db/database.py`), which builds the
async engine + sessionmaker and **creates the tables** (`Session`, `Message`) if they don't exist.
There is no separate migration step for first run. The backend therefore expects the database to be
**up and reachable before** `uvicorn` starts.

## Useful commands

```bash
docker compose up -d        # start in background
docker compose logs -f      # follow logs
docker compose ps           # status / health
docker compose down         # stop (keeps data in ./data)
```

To wipe all stored sessions/history, stop the container and delete `database/data/`.

## Troubleshooting

- **Backend can't connect at startup:** ensure the container is healthy (`docker compose ps`) and
  that `DATABASE_URL` host/port/credentials match `database/.env`.
- **Port already in use:** change `POSTGRES_PORT` in `database/.env` and the port in `DATABASE_URL`.
