# Deployment

> **Status:** the Docker setup predates the new Vue frontend. The `web` service still builds from
> `frontend/Dockerfile` and serves through `frontend/nginx.conf`. Both were removed together with the
> old SvelteKit frontend, so `docker compose up --build` currently fails at `web`. The `backend` and
> `postgres` services are unaffected. This guide describes the intended setup until `web` is rebuilt.

## The stack

One root `docker-compose.yml`, configured by one root `.env`:

```
             ┌────────── web (nginx, :WEB_PORT) ──────────┐
 Browser ───▶│  /         → static frontend (built SPA)   │
             │  /api/...  → backend:8000                  │
             └───────────────────┬────────────────────────┘
                     backend (uvicorn) ──▶ postgres (volume db_data)
                          └──▶ GraphDB (external, VPN)   └──▶ LLM API
```

Because nginx serves the frontend and proxies `/api`, the app needs no absolute backend URL and no
CORS setup. `cloudflared` is an optional fourth service (see [Public link](#public-link-cloudflare-tunnel)).

## Configure the host

```bash
cp .env.example .env
```

Set at least:

| Variable | Note |
|----------|------|
| `BLABLADOR_API_KEY` | Secret. |
| `POSTGRES_PASSWORD` | Change the default. |
| `GRAPHDB_BASE_URL`, `GRAPHDB_REPOSITORY` | Must be reachable from the host. The default server needs the **university VPN**, which is the most common reason a deployment "doesn't work". |
| `WEB_PORT` | Public port (default `80`). |
| `UVICORN_WORKERS` | Backend worker processes. |

`DATABASE_URL` is built from the `POSTGRES_*` values inside `docker-compose.yml`, so don't set it
separately. All other variables are described in [Configuration](./configuration.md).

**One-time prerequisites:** these are not run by the containers.

- The generated prompts (`backend/src/resources/prompts/*.md`) must be committed.
- The Lucene index must exist in GraphDB.

See [Knowledge graph › Onboarding](./knowledge-graph.md#onboarding-a-new-knowledge-graph).

## Deploy and check

```bash
docker compose up -d --build
curl -s http://localhost:${WEB_PORT}/api/v1/health
```

- **Startup order:** `postgres` starts first (with a healthcheck), then `backend`, then `web`.
- **Database tables:** the backend creates them on first start.
- **Health check:** `/api/v1/health` returning `"ok"` means GraphDB and the LLM are reachable.
  `degraded` or `down` almost always means a VPN or API key problem.
  - The container healthcheck only checks that the process is alive. A container can be "healthy"
    while the API reports `down`.

## Releasing

- **Version scheme:** semantic versioning with a git tag `vMAJOR.MINOR.PATCH`. The same tag names
  the release and any pushed images.

**Steps:**

1. Run the checks on a clean `main`: `pytest`, `mypy src/` and `npm run check`.
2. Note the changes in `CHANGELOG.md`.
3. Bump the version in `frontend/package.json` and in `backend/src/main.py` (`FastAPI(version=…)`).
4. Commit, then tag and push: `git tag -a vX.Y.Z -m vX.Y.Z && git push origin main --tags`.
5. Deploy on the host with `docker compose up -d --build`.

**Rollback:** check out the previous tag and run `docker compose up -d --build`. Postgres data lives
in the `db_data` volume and survives this.

- **Never use `down -v`:** `docker compose down -v` deletes all sessions.
- **Schema changes:** tables are only created, never migrated. A release that changes the schema
  can't simply be rolled back, so call schema changes out in the changelog.

## TLS

The stack serves plain HTTP on `WEB_PORT`. For a public deployment, either terminate HTTPS in the
`web` nginx or put the stack behind a reverse proxy that handles TLS.

## Public link (Cloudflare Tunnel)

For a quick shareable `https://` URL without port forwarding or firewall changes, use the optional
`cloudflared` service. It makes an outbound connection to Cloudflare, and TLS is handled by
Cloudflare.

```bash
docker compose --profile tunnel up -d cloudflared
docker compose logs cloudflared | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com'
docker compose stop cloudflared       # take it offline again
```

Caveats:

- **The URL is random** and changes on every restart. A stable URL needs a Cloudflare account and a
  named tunnel.
- **Anyone with the link** can use the app and spend your LLM key. Stop it when you're done.
- **The host must stay awake** and on the VPN.

**Troubleshooting:**

- **`failed to dial to edge with quic`:** the network blocks outbound UDP. The compose file already
  forces `--protocol http2` (TCP).
- **Endless `307` redirects through the tunnel:** a trailing-slash redirect is built with `http://`
  behind the proxy, and the browser blocks it as mixed content. Define routes without a trailing
  slash (`@router.post("")`, not `"/"`).
