# GraphDB & SPARQL

The knowledge graph lives in **GraphDB**. The backend runs SPARQL queries against it over HTTP.

## Endpoint

The SPARQL endpoint is built from two settings (see [Configuration](./configuration.md)):

```
{GRAPHDB_BASE_URL}/repositories/{GRAPHDB_REPOSITORY}
```

By default this is
`http://graphdb-lehre.inf-bb.uni-jena.de:32833/repositories/SWEPLARGE`.

`SparqlService` (`backend/src/services/sparql_service.py`) issues an HTTP `GET` with the query as the
`query` parameter and `Accept: application/sparql-results+json`. Response handling:

- **HTTP 400** → `SparqlQueryException`: GraphDB rejected the query (syntax/semantics). The error
  body is fed back to the LLM so it can fix and retry (see
  [Architecture › agentic tool loop](./architecture.md#the-agentic-tool-loop)).
- **Other non-200** → `SparqlDatabaseStatusCode`: an infrastructure problem (endpoint down,
  repository missing, auth) — not retried.

Only read queries are run on the chat path; `sparql_utils.validate_query()` rejects mutating
operations (`INSERT`/`DELETE`/`CONSTRUCT`/`DROP`).

## Lucene full-text connectors

Full-text lookups (matching free-text names of species, cities, gardens) use GraphDB **Lucene
connectors**. Their definitions are SPARQL files in `backend/src/resources/lucene/`:

- `species_lucene.rq`
- `city_lucene.rq`
- `botanicalGarden_lucene.rq`

`backend/src/services/lucene_setup.py` (with `lucene_service.py`) is a **standalone utility** —
not part of the running API — that creates/recreates these connector indices in GraphDB from the
`.rq` files. Run it once against a fresh repository (or after changing a connector definition) so
full-text search works. It needs the same `GRAPHDB_*` configuration as the backend.

## The full-table query

`GET /chat/full_table` runs a fixed query from `FULL_TABLE_QUERY_PATH`
(`backend/src/resources/queries/full_table.rq`) and maps it to the columns in `FULL_TABLE_COLUMNS`.
This is a non-LLM, predefined tabular view of the data. See [API reference](./api_reference.md).

## Running ad-hoc SPARQL with the `sparql-query` skill

For exploring the graph during development, the repo includes a read-only Claude Code skill at
`.claude/skills/sparql-query/`. It runs a query against the **same endpoint** (read from
`backend/.env`) and prints the JSON results.

Run it directly:

```bash
# single-line query as an argument
bash .claude/skills/sparql-query/run_query.sh 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'

# multi-line query via stdin / heredoc
bash .claude/skills/sparql-query/run_query.sh <<'SPARQL'
SELECT DISTINCT ?c (COUNT(?s) AS ?n)
WHERE { ?s a ?c } GROUP BY ?c ORDER BY DESC(?n) LIMIT 20
SPARQL

# connectivity check
bash .claude/skills/sparql-query/run_query.sh 'ASK {}'
```

It is **read-only**: queries containing `INSERT`/`DELETE`/`DROP`/`CLEAR`/`LOAD`/`CREATE`/etc. are
refused before any request is sent. Inside Claude Code you can also invoke it as the
`/sparql-query` skill. See the skill's own `SKILL.md` for details.

## Data model note

The `SWEPLARGE` repository models observations using a **semantic-units / statement-unit** pattern
(e.g. `http://example.com/semunit/observationStatementUnit`) layered with the W3C **Time** ontology
and OBO **PPO** (plant phenology) / **IAO** classes — rather than flat
`species → flowersOn → date` triples. Explore the predicates/classes first (see the skill examples
above) before writing queries.
