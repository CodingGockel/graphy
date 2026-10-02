# Graphy

Graphy is a chat interface for **SPARQL agents**: ask a question in natural language, an LLM writes
and runs SPARQL against a **GraphDB** knowledge graph, and you get the answer back in plain language.

It started as *DataExplorer*, a Q&A app for the PhenObs plant-phenology knowledge graph. It is now
being turned into a generic UI that works with any knowledge graph. The backend is configured for
PhenObs today; [docs/knowledge-graph.md](./docs/knowledge-graph.md) explains how to point it at
another graph.

| Part | Tech | Folder |
|------|------|--------|
| Frontend | Vue 3 + Vite | `frontend/` |
| Backend | FastAPI, agentic LLM tool loop | `backend/` |
| Chat history | PostgreSQL (Docker) | `database/` |
| Knowledge graph | GraphDB (external) | — |
| LLM | Blablador (OpenAI-compatible API) | — |

```
 Browser ──▶ Frontend (Vue) ──/api/v1──▶ Backend (FastAPI) ──▶ LLM API (Blablador)
                                                │
                                                ├──▶ GraphDB (SPARQL, Lucene)
                                                └──▶ PostgreSQL (sessions, history)
```

## Quick start (local development)

You need Docker, Python 3.12, Node.js 20.19+, a **Blablador API key**, and network access to
GraphDB. The default GraphDB server requires the university VPN.

```bash
# 1. Database
cd database && cp .env.example .env && docker compose up -d

# 2. Backend  → http://localhost:8000 (API docs at /docs)
cd ../backend
python -m venv ../.swep-venv && source ../.swep-venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in BLABLADOR_API_KEY
uvicorn src.main:app --reload

# 3. Frontend → http://localhost:5173
cd ../frontend && npm install && npm run dev
```

Details and troubleshooting are in [docs/setup.md](./docs/setup.md).

## Documentation

Start at [docs/README.md](./docs/README.md).