# Knowledge graph

The backend talks to a **GraphDB** repository over its SPARQL endpoint. Two things are tailored to
each knowledge graph (KG): the **prompts**, which tell the LLM the schema and how to query it, and
the **Lucene index**, which lets the LLM resolve names to real URIs. Everything else is generic.

## How queries run

Endpoint: `{GRAPHDB_BASE_URL}/repositories/{GRAPHDB_REPOSITORY}` (see [Configuration](./configuration.md)).

`SparqlService` sends the query as an HTTP `GET` with `Accept: application/sparql-results+json`:

- **HTTP 400** → `SparqlQueryException`: the query itself is wrong. The error goes back to the LLM,
  which fixes the query and retries.
- **Other non-200 or unreachable** → `SparqlDatabaseStatusCode` / `SparqlDatabaseException`: an
  infrastructure problem. The request is aborted (HTTP 502 / 503).

Only read queries are allowed: `validate_query()` rejects `INSERT`, `DELETE`, `CONSTRUCT` and `DROP`
(as whole words, in any case; string literals, IRIs and comments are ignored).

## Entity resolution (Lucene)

The `resolve_entity` tool searches the GraphDB Lucene connector `entity_lucene`, a full-text index
over `rdfs:label`. The connector is defined in `backend/src/resources/lucene/entity_lucene.rq`. It
lists the entity types to index, i.e. the kinds of things users refer to by name. Helper queries for
choosing those types are in `resources/lucene/discovery/`.

If nothing is found, the LLM is told to fall back to a `FILTER(CONTAINS(LCASE(?label), …))` query
instead of inventing a URI.

## Exploring the graph: the `sparql-query` skill

`.claude/skills/sparql-query/` runs a **read-only** query against the endpoint configured in
`backend/.env` and prints the JSON results. Mutating queries are refused before anything is sent.
Inside Claude Code it is available as `/sparql-query`.

```bash
bash .claude/skills/sparql-query/run_query.sh 'ASK {}'      # connectivity check
bash .claude/skills/sparql-query/run_query.sh <<'SPARQL'
SELECT ?c (COUNT(?s) AS ?n) WHERE { ?s a ?c } GROUP BY ?c ORDER BY DESC(?n) LIMIT 20
SPARQL
```

## Onboarding a new knowledge graph

All commands run from `backend/` with the virtualenv active. Both scripts read the live repository.
An empty repository therefore produces an empty prompt and an empty index.

**Requirements for the data:**

- The repository is created and loaded with data.
- Entities that users refer to by name carry `rdfs:label`.
- No T-Box is needed. The schema is derived from the data itself: which types have instances, and
  which predicate points to what. Prefixes are derived from the namespaces in the data.

### 1. Point the backend at the repository

```dotenv
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=<your-repo>
```

### 2. Write the KG profiles

The prompts are composed from a KG-agnostic skeleton and a hand-written profile per KG. Edit the
profiles in `src/resources/prompts/templates/`:

| File | Purpose | Edit per KG? |
|------|---------|--------------|
| `generic_rules.md` | Query rules and tool usage; markers `{{KG_PROFILE}}`, `{{SCHEMA}}` | rarely |
| `kg_profile.md` | **Query profile:** domain, entities and URI patterns, verified example queries, datatype gotchas, when to resolve entities or ask for clarification | **yes** |
| `generic_answer.md` | Answer rules; marker `{{KG_ANSWER_PROFILE}}` | rarely |
| `kg_answer_profile.md` | **Answer profile:** how to present values (units, dates), terminology, label clean-up, the "related information you can offer" menu | **yes** |

**Tips:**

- `kg_profile.md` matters most for query quality. Include a few example queries you have verified
  (`sparql-query` skill or GraphDB Workbench).
- Leave the `{{SCHEMA}}` marker in place.
- HTML comments in the templates are stripped and never reach the model.

### 3. Build the prompts

```bash
python -m src.services.build_prompt
```

This script:

- **Extracts the schema:** runs `src/resources/schema/classes.rq` and `properties.rq` against the
  data.
- **Derives prefixes:** writes them to `src/resources/schema/prefixes.json`.
- **Writes the prompts:** `src/resources/prompts/system_prompt.md` and `answer_system_prompt.md`.
  Never edit these two by hand.

Check the printed counts (prefixes, classes, properties), and confirm `system_prompt.md` has no
leftover `{{…}}` markers.

### 4. Build the Lucene index

**a) Find the types of your named entities.**

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?type (COUNT(?s) AS ?n) WHERE { ?s a ?type ; rdfs:label ?l }
GROUP BY ?type ORDER BY DESC(?n)
```

**b) Set them in `src/resources/lucene/entity_lucene.rq`.**

```json
"types": ["http://example.org/SomeNamedEntityClass", "http://example.org/AnotherOne"]
```

Keep the connector name `entity_lucene` and the field `label`; `LuceneService` depends on both.

**c) Create the connector.**

```bash
python -m src.services.lucene_setup     # expect {'entity': {'status': 'ok'}}
```

**d) Verify the index.**

```sparql
PREFIX luc: <http://www.ontotext.com/connectors/lucene#>
PREFIX inst: <http://www.ontotext.com/connectors/lucene/instance#>
SELECT ?entity ?score WHERE {
  ?s a inst:entity_lucene ; luc:query "label:(somename* OR somename~1)" ; luc:entities ?entity .
  ?entity luc:score ?score .
} ORDER BY DESC(?score) LIMIT 5
```

### 5. Test end to end

Ask a question that names an entity. `backend/logs/server.log` should show `resolve_entity`, then
`execute_sparql_query` using a real URI, then the final answer call.

### When to re-run what

| Change | Re-run |
|--------|--------|
| Schema changed (classes, properties, prefixes) | `build_prompt` |
| A template or profile changed | `build_prompt` |
| New data, same types | nothing (the connector updates itself) |
| Indexed entity types changed | `lucene_setup` |

### Troubleshooting

| Symptom | Cause |
|---------|-------|
| Empty class/property tables in the prompt | Repository empty, or `GRAPHDB_REPOSITORY` points to the wrong one. |
| `resolve_entity` never finds anything | `types` in `entity_lucene.rq` don't match the data exactly (watch capitalization), or the connector wasn't created. |
| `luc:query` says "no such connector" | `lucene_setup` didn't run successfully. |
| An ugly auto-generated prefix | Add a mapping to `WELL_KNOWN` in `src/services/build_prompt.py` and re-run. |

## The current KG: PhenObs

The configured repository `SWEPLARGE` holds plant-phenology observations from 15 botanical gardens
(2019–2024). Its data model is not flat (`species → flowersOn → date`). It uses
**semantic units / statement units**, combined with the W3C Time ontology and OBO PPO/IAO classes.
Explore the classes and predicates before writing queries by hand.

PhenObs-specific parts of the backend:

- **Profiles:** `kg_profile.md` and `kg_answer_profile.md`
- **Tool:** `load_phenobs_papers`
- **Full table:** the `/table` endpoint
- **Test questions:** [test-questions.md](./test-questions.md)
