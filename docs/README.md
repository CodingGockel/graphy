# Documentation

Documentation for **DataExplorer** — a biodiversity question-answering app (natural language →
SPARQL → GraphDB → answer). Start with the project [README](../README.md) for the high-level
overview and quick start.

## Contents

### Understand the system
- [Architecture](./architecture.md) — components, request flow, the agentic tool loop, persistence,
  error handling.

### Set it up
- [Backend setup](./backend_setup.md) — run the FastAPI backend.
- [Database setup](./database_setup.md) — PostgreSQL via Docker Compose.
- [Frontend setup](./frontend_setup.md) — run the SvelteKit frontend.
- [Configuration](./configuration.md) — every `.env` variable (backend + database).

### Ship it
- [Releasing](./releasing.md) — versioning, building images, deploying the Docker stack, smoke
  tests, and rollback.
- [Cloudflare Tunnel](./cloudflare_tunnel.md) — expose the running app on a temporary public
  `https://` URL for sharing/testing, plus troubleshooting.

### Build against it
- [API reference](./api_reference.md) — all HTTP endpoints and schemas.
- [Chat & sessions guide](./frontend_chat_sessions.md) — the client conversation workflow.
- [GraphDB & SPARQL](./graphdb_sparql.md) — endpoint, Lucene connectors, the ad-hoc query skill.

### Test it
- [Test questions](./backend_test_questions.md) — sample questions for manual testing.

## Conventions

- Documentation is written in English.
- Backend/model configuration is **`.env`-only and read-only at runtime** — there is no settings
  API.
