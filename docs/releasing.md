# Releasing

How to cut a release of **DataExplorer** and deploy the full stack with Docker. The stack is three
services orchestrated by the root [`docker-compose.yml`](../docker-compose.yml): `web` (nginx —
serves the static frontend and proxies `/api`), `backend` (FastAPI/uvicorn), and `postgres`. See the
[README "Production / Docker"](../README.md#production--docker) section for the topology diagram.

This guide assumes a single-host deployment via Docker Compose. Adapt the build/push steps if you
deploy to a registry-based platform (Kubernetes, Nomad, etc.).

## Prerequisites

- Docker and the Compose plugin on the deploy host (`docker --version`, `docker compose version`).
- **Network route to GraphDB.** The backend calls an external GraphDB (`GRAPHDB_BASE_URL`) that is
  gated behind the **university VPN**. The deploy host must be able to reach it, or every chat
  request fails. This is the single most common deployment blocker — verify it first.
- A **Blablador API key** and the GraphDB repository name.
- The generated prompt files committed in the repo
  (`backend/src/resources/prompts/system_prompt.md` and `answer_system_prompt.md`) and an existing
  GraphDB **Lucene entity index**. These are one-time prerequisites, not part of container startup
  (see [One-time data prerequisites](#one-time-data-prerequisites)).

## Versioning

Use **semantic versioning** with a `vMAJOR.MINOR.PATCH` git tag (e.g. `v1.2.0`).

- **MAJOR** — incompatible API or data changes (e.g. a changed `/api/v1` contract, a breaking KG
  schema change).
- **MINOR** — backwards-compatible features.
- **PATCH** — backwards-compatible fixes.

The same tag names the release, the git tag, and (if you push images) the Docker image tags, so a
deployed version is always traceable back to a commit.

## Release steps

### 1. Pick the release commit and verify it

Release from `main` with a clean working tree. Run the checks locally (per the project working
agreement these are run by a human, not by automation-in-the-loop):

```bash
# Backend
cd backend && source .swep-venv/bin/activate
pytest && mypy src/

# Frontend
cd ../frontend && npm install && npm run check
```

> **Lockfile note:** the frontend was migrated to `@sveltejs/adapter-static`. If `package-lock.json`
> is out of sync with `package.json`, the `web` image build (`npm ci`) fails. Run `npm install` and
> commit the updated lockfile **before** tagging.

### 2. Update the changelog and bump the version

- Summarise what changed since the previous tag (features, fixes, breaking changes, migration
  notes) in `CHANGELOG.md` (create it if absent) under the new version heading.
- Bump `version` in `frontend/package.json` and `version` in `backend/src/main.py`
  (`FastAPI(..., version="...")`) to match the tag.

### 3. Tag the release

```bash
git commit -am "Release v1.2.0"
git tag -a v1.2.0 -m "v1.2.0"
git push origin main --tags
```

### 4. Build the images

From the repo root, on the deploy host (or a build host if you push to a registry):

```bash
docker compose build
```

This builds:
- `backend` from [`backend/Dockerfile`](../backend/Dockerfile) (python:3.12-slim, non-root,
  uvicorn).
- `web` from [`frontend/Dockerfile`](../frontend/Dockerfile) (multi-stage: `npm run build` →
  nginx serving the static SPA + `/api` proxy).

To publish to a registry instead of building on the host, tag and push, e.g.:

```bash
docker tag app-backend registry.example.org/dataexplorer/backend:v1.2.0
docker tag app-web     registry.example.org/dataexplorer/web:v1.2.0
docker push registry.example.org/dataexplorer/backend:v1.2.0
docker push registry.example.org/dataexplorer/web:v1.2.0
```

### 5. Configure the environment on the host

The whole stack reads a **single root `.env`** (template: [`.env.example`](../.env.example)). It is
gitignored — create it on the host, never commit it.

```bash
cp .env.example .env
```

Then set, at minimum:

| Variable | Notes |
|----------|-------|
| `BLABLADOR_API_KEY` | Secret. |
| `POSTGRES_PASSWORD` | **Change from the default** before any real deployment. |
| `GRAPHDB_BASE_URL`, `GRAPHDB_REPOSITORY` | Must be reachable from the host (VPN). |
| `WEB_PORT` | Host port for the public entrypoint (default `80`). |
| `CORS_ALLOW_ORIGINS` | Leave `[]` for the same-origin nginx setup; set a JSON list only if the frontend is served from another origin. |
| `UVICORN_WORKERS` | Backend worker processes. |

`DATABASE_URL` is **derived** from the `POSTGRES_*` values inside `docker-compose.yml`, so there is a
single source of truth — don't set it separately.

### 6. Deploy

```bash
docker compose up -d
# (or `docker compose up -d --build` to build and start in one step)
```

Compose starts `postgres` first and waits for its healthcheck, then `backend`, then `web`. The
backend creates its tables on first start (`init_db()`); there is no separate migration step for the
current schema.

### 7. Smoke test

```bash
# Backend readiness (checks GraphDB + LLM connectivity):
curl -s http://localhost:${WEB_PORT}/api/v1/health | jq

# Frontend:
open http://localhost:${WEB_PORT}/
```

- `health` returning `{"status": "ok"}` means GraphDB and the LLM are both reachable.
- `degraded`/`down` almost always means the **VPN/GraphDB route** or the **Blablador key** is wrong
  — the app process itself is still up (the container's own healthcheck is liveness-only, so the
  container can be "healthy" while readiness is `down`).
- In the UI: load the page, send a question, confirm an answer + data come back, and check the
  results table / map views.

## Rollback

Because images are tagged per release and Postgres data lives in the `db_data` named volume
(independent of the app containers), rolling back the app is just redeploying the previous tag:

```bash
git checkout v1.1.0      # previous tag
docker compose up -d --build
```

Caveats:
- **Database schema:** the backend auto-creates tables but does not run down-migrations. A release
  that changed the schema may not be safely rolled back without a data migration. Call out schema
  changes explicitly in the changelog.
- **Data volume:** `docker compose down` keeps `db_data`; `docker compose down -v` **deletes it**.
  Never use `-v` on a deploy host unless you intend to wipe all sessions/history.

## One-time data prerequisites

These depend on GraphDB and are **not** run by the containers at startup:

- **Prompts** — `backend/src/resources/prompts/system_prompt.md` and `answer_system_prompt.md` are
  generated by `build_prompt.py` and committed. Regenerate (and commit) only when the KG schema or a
  prompt template changes.
- **Lucene entity index** — created in GraphDB by `lucene_setup.py`. Must exist before the
  `resolve_entity` tool works.

Both require GraphDB access; run them as a maintenance step when the knowledge graph changes, not on
every release.

## TLS

TLS is currently **deferred**: the stack serves plain HTTP on `WEB_PORT`. Before a public release,
either:

- terminate HTTPS in the `web` nginx (a commented `:443` server block is in
  [`frontend/nginx.conf`](../frontend/nginx.conf) — add certs and redirect `:80` → `:443`), or
- run the stack behind an upstream reverse proxy / load balancer that terminates TLS and forwards to
  `WEB_PORT`.

## Release checklist

- [ ] `main` is clean; backend `pytest`/`mypy` and frontend `npm run check` pass.
- [ ] `package-lock.json` is in sync (`npm install` committed).
- [ ] `CHANGELOG.md` updated; versions bumped in `frontend/package.json` and `backend/src/main.py`.
- [ ] Git tag `vX.Y.Z` created and pushed.
- [ ] Host `.env` configured (secrets set, `POSTGRES_PASSWORD` changed, GraphDB reachable).
- [ ] `docker compose up -d` brings all three services up healthy.
- [ ] `/api/v1/health` returns `ok`; UI smoke test passes.
- [ ] TLS handled (own nginx or upstream proxy) for public deployments.
