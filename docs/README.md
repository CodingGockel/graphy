# Documentation

| Doc | What's in it |
|-----|--------------|
| [Setup](./setup.md) | Run database, backend and frontend locally; tests and checks. |
| [Configuration](./configuration.md) | Every `.env` variable (backend, database, frontend, Docker). |
| [Architecture](./architecture.md) | How the parts fit together; the agentic tool loop. |
| [API](./api.md) | HTTP endpoints, schemas, and how a client drives a chat session. |
| [Frontend](./frontend.md) | Requirements, design rules and structure of the Vue app. |
| [Knowledge graph](./knowledge-graph.md) | GraphDB, SPARQL, entity resolution, onboarding a new KG. |
| [Deployment](./deployment.md) | Docker stack, releases, public access via Cloudflare Tunnel. |
| [Test questions](./test-questions.md) | Verified questions and answers for the PhenObs KG. |

Other folders:

- [`plans/`](./plans/): plans for upcoming work, e.g. the [streaming rework](./plans/streaming-rework.md).
- [`designs/`](./designs/): logo sources (`graphy-icon.svg`, `graphy-wordmark.svg`) and the PNG drafts.
- [`presentation/`](./presentation/): Slidev slides from the DataExplorer backend talk.

## Conventions

- Docs are written in English (plans may be in German).
- Backend configuration is `.env`-only and read-only at runtime. There is no settings API.
- When code changes behavior, update the matching doc in the same change.
