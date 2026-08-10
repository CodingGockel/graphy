# Onboarding a New Knowledge Graph

This guide walks through everything needed to point the chat backend at a **new GraphDB
knowledge graph (KG)** — configuring it, regenerating the schema-driven prompt with the
**schema extractor**, and building the **Lucene** entity-resolution index.

The chat answers questions by running an agentic LLM tool-loop that generates SPARQL. Two
things in that loop are KG-specific and must be (re)built per KG:

1. **The prompts** — a query prompt that tells the LLM the KG's schema (prefixes, classes,
   properties) and how to query it, and an answer prompt that tells it how to present results. Both
   are composed from a KG-agnostic skeleton + a hand-written per-KG profile + an auto-extracted
   schema block by the schema extractor (`build_prompt.py`).
2. **The `entity_lucene` index** — lets the LLM resolve names ("Jena", "Achillea millefolium") to
   real URIs instead of guessing them. Built by `lucene_setup.py`.

> All commands run from `backend/` with the virtualenv active:
> ```bash
> cd backend
> source .swep-venv/bin/activate
> ```

---

## Prerequisites

- **GraphDB is running** and reachable, with the new repository **created and loaded with data**.
  Both scripts read live from the repo — an empty repo produces an empty prompt/index.
- The data uses **`rdfs:label`** on the entities users refer to by name (species, places, …) — both
  the schema block and the Lucene index lean on labels.
- **No T-Box required.** The extractor derives the schema **from the data itself** — which types
  actually have instances, and which predicate points at which kind of object — so a graph with no
  declared `owl:Class` / `owl:*Property` works fine. Prefixes are likewise derived from the
  namespaces that appear in the data (GraphDB's `/namespaces` endpoint is *not* used; on most repos
  it returns only engine-internal prefixes, not the domain vocabularies).

---

## Step 1 — Point the backend at the new repository

Edit `.env`:

```dotenv
GRAPHDB_BASE_URL=http://localhost:7200
GRAPHDB_REPOSITORY=<your-new-repo>
```

Both scripts and the running server use these. Nothing else in `.env` needs to change for a new KG
(the prompt/template paths have sensible defaults in `src/util/config.py`).

---

## Step 2 — Write the per-KG profiles

Both prompts are composed from **two layers**: a KG-agnostic skeleton (rarely touched) and a
hand-written **per-KG profile** (the part you adapt). `build_prompt.py` (Step 3) fills the markers
and writes the final `system_prompt.md` and `answer_system_prompt.md` — **do not hand-edit those
generated files.**

Templates live in `src/resources/prompts/templates/`:

| File | Layer | Edit per KG? |
|------|-------|--------------|
| `generic_rules.md` | KG-agnostic query rules + tool usage; markers `{{KG_PROFILE}}`, `{{SCHEMA}}` | rarely |
| `kg_profile.md` | **per-KG query profile** (fills `{{KG_PROFILE}}`) | **yes** |
| `generic_answer.md` | KG-agnostic answer rules; marker `{{KG_ANSWER_PROFILE}}` | rarely |
| `kg_answer_profile.md` | **per-KG answer profile** (fills `{{KG_ANSWER_PROFILE}}`) | **yes** |

**`kg_profile.md`** — the most important file for query quality. Describe, for *this* KG:
- **Domain** — what the KG is about.
- **Entity map & URI patterns** — the real-world entities, their classes and how URIs look.
- **Query patterns** — the "happy path(s)" for traversing the model, ideally as a few **verified
  example SPARQL queries** (use the `sparql-query` skill / GraphDB Workbench to confirm them).
- **Datatype gotchas**, **entity-resolution guidance** (which kinds to resolve vs. filter), and
  **KG-specific clarification cases**. An "Administrator notes" section is there for extra context.

**`kg_answer_profile.md`** — how to present results for this KG: value interpretation (e.g. units,
date conversions), terminology mapping, label/URI clean-up (e.g. a Wikidata-ID → name table), and
the **"Related information you can offer"** menu the answer uses to suggest further exploration.
Replace the phenology content with your KG's equivalents.

> The `{{SCHEMA}}` marker in `generic_rules.md` is where the auto-extracted prefix/class/property
> tables are injected in Step 3 — leave it in place. HTML comments in the templates are stripped
> during composition, so they never reach the model.

---

## Step 3 — Compose the prompts (schema extractor)

This extracts the live KG's schema over SPARQL and writes **both** final prompts by filling the
markers in the templates.

```bash
python -m src.services.build_prompt
```

What it does:
- Runs the **data-based** discovery queries in `src/resources/schema/` against the repo:
  `classes.rq` (types that have instances, with counts) and `properties.rq` (each predicate with
  the kind of object it points at — the real datatype, e.g. `xsd:int` vs `xsd:integer`, or
  `iri`/`bnode`).
- **Derives prefixes** from the namespaces that actually appear (well-known vocabularies get
  conventional prefixes; the rest are auto-named). Writes the map to `src/resources/schema/prefixes.json`.
- Renders a markdown **`{{SCHEMA}}`** block (PREFIX list + Classes table + Properties table).
- Composes `generic_rules.md` + `kg_profile.md` + that schema block → `system_prompt.md`, and
  `generic_answer.md` + `kg_answer_profile.md` → `answer_system_prompt.md`.

It prints what it wrote — sanity-check the counts before going live:

```
wrote src/resources/schema/prefixes.json (11 prefixes, 49 classes, 38 property/datatype rows)
wrote src/resources/prompts/system_prompt.md
wrote src/resources/prompts/answer_system_prompt.md
```

Open `system_prompt.md` and confirm the schema block looks right (prefixes/classes/properties match
the KG, the example queries from your profile are intact, no leftover `{{…}}` markers). Re-run this
script whenever the KG's schema, the templates, or a profile changes.

---

## Step 4 — Build the Lucene entity-resolution index

The `resolve_entity` tool searches a Lucene full-text index over `rdfs:label`. The index covers only
the **named-entity types** you list — the kinds of things users refer to by name (species, places,
etc.). You must set those types for the new KG.

**4a. Find the types your named entities actually carry.** Run (GraphDB Workbench or the
`sparql-query` skill):

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?type (COUNT(?s) AS ?n) WHERE { ?s a ?type ; rdfs:label ?l }
GROUP BY ?type ORDER BY DESC(?n)
```

Pick the types that correspond to entities users name (not internal/structural classes).

**4b. Edit `src/resources/lucene/entity_lucene.rq`** — put those URIs in the `types` array:

```json
"types": [
    "http://example.org/SomeNamedEntityClass",
    "http://example.org/AnotherNamedEntityClass"
]
```

(`languages: []` indexes labels of all languages — leave it.) The connector instance name
`entity_lucene` and the `label` field should stay as-is; `LuceneService.search()` depends on them.

**4c. Create the connector:**

```bash
python -m src.services.lucene_setup
```

This drops any existing `entity_lucene` connector and recreates it, triggering GraphDB to index the
matching entities. Expect `{'entity': {'status': 'ok'}}`. Lucene itself needs no installation — it's
GraphDB's built-in Connectors plugin (enabled by default). Re-run this only when the data or the
`types` list changes; otherwise the connector auto-updates as data changes.

**4d. Verify the index:**

```sparql
PREFIX luc: <http://www.ontotext.com/connectors/lucene#>
PREFIX inst: <http://www.ontotext.com/connectors/lucene/instance#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?entity ?label ?score WHERE {
  ?s a inst:entity_lucene ;
     luc:query "label:(<some-known-name>* OR <some-known-name>~1)" ;
     luc:entities ?entity .
  ?entity rdfs:label ?label .
  ?entity luc:score ?score .
} ORDER BY DESC(?score) LIMIT 5
```

Ranked rows = working. Empty = the `types` don't match the data (revisit 4a/4b). *"connector …
does not exist"* = `lucene_setup` didn't run successfully.

---

## Step 5 — End-to-end check

Start the server and ask a question that names an entity:

```bash
uvicorn src.main:app --reload
# POST /api/v1/chat  with a question that mentions a specific entity by name
```

In `backend/logs/server.log` you should see the loop:
1. the LLM calls **`resolve_entity`** for the name → gets candidate URIs,
2. then **`execute_sparql_query`** using one of those real URIs,
3. and the final answer is produced by the separate answer call.

If `resolve_entity` finds nothing, the LLM is instructed to fall back to a
`FILTER(CONTAINS(LCASE(?label), "…"))` query rather than invent a URI — so the chat still works, just
less precisely.

---

## When the KG changes later

| Change | Re-run |
|---|---|
| Schema changed (new/renamed classes or properties), or new prefixes | `python -m src.services.build_prompt` |
| Data changed (new instances) | nothing — the Lucene connector auto-updates |
| Named-entity **types** to index changed, or you edited `entity_lucene.rq` | `python -m src.services.lucene_setup` |
| Edited a template or profile (`kg_profile.md`, `kg_answer_profile.md`, `generic_*`) | `python -m src.services.build_prompt` (re-composes both prompts) |

---

## Onboarding checklist

- [ ] GraphDB running; new repo created and loaded with data
- [ ] `.env`: `GRAPHDB_BASE_URL`, `GRAPHDB_REPOSITORY` set to the new repo
- [ ] Wrote `kg_profile.md` (domain, entity map, verified example queries, rules) — kept `{{SCHEMA}}` in `generic_rules.md`
- [ ] Wrote `kg_answer_profile.md` (value/terminology/label rules, "related information" menu)
- [ ] `python -m src.services.build_prompt` → checked counts, `system_prompt.md` and `answer_system_prompt.md`
- [ ] Set `types` in `entity_lucene.rq` from the type-discovery query
- [ ] `python -m src.services.lucene_setup` → `status: ok`, verified with a `luc:query`
- [ ] End-to-end chat test shows `resolve_entity` → `execute_sparql_query` with a real URI

---

## Troubleshooting

- **Empty class/property tables in `system_prompt.md`.** The discovery queries returned nothing —
  usually the repo is empty/not loaded, or `GRAPHDB_REPOSITORY` points at the wrong repo. The
  queries are data-based (`?s a ?class`), so a missing T-Box is *not* the cause.
- **`build_prompt` queries fail / can't connect.** Check `GRAPHDB_BASE_URL` / `GRAPHDB_REPOSITORY`
  and that GraphDB is up. The script uses the same `SparqlService` as the app.
- **A prefix in the schema block looks auto-generated/ugly.** Namespaces without a well-known prefix
  are auto-named; add a mapping to `WELL_KNOWN` in `src/services/build_prompt.py` if you want a nicer
  one, then re-run.
- **`resolve_entity` always returns nothing.** The `types` in `entity_lucene.rq` don't match the
  data's actual `rdf:type`s (run the type-discovery query), or the connector wasn't built.
- **`luc:query` errors with "no such connector".** Run `python -m src.services.lucene_setup`; ensure
  it printed `status: ok`.
- **Watch exact type URIs.** Indexing matches `rdf:type` exactly — a capitalization or namespace
  mismatch (e.g. `ENVO_BotanicalGarden` vs `ENVO_botanicalGarden`) silently indexes nothing.
