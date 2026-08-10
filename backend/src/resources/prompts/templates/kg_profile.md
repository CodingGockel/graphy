<!--
  PER-KG PROFILE for the phenology knowledge graph (GraphDB repository SWEPLARGE).
  This is the single hand-maintained source of graph-specific knowledge for query
  generation. Everything here was verified against the live endpoint. The {{SCHEMA}}
  tables (prefixes / classes / properties) are appended automatically by build_prompt.py
  and complement — do not duplicate — the patterns described here.
  When migrating to another graph, replace this whole file.
-->
# Knowledge Graph: Plant Phenology in Botanical Gardens

This graph holds **phenological observations of plants** (when they flower, unfold leaves, senesce)
recorded in ~15 botanical gardens across several countries, over the years **2019–2024**. One record
describes one plant of one species, in one garden, in one year.

The graph is **heavily reified** ("Semantic-Unit" model): the same fact is stored twice — once in a
verbose OBI/IAO measurement chain, and once as a clean reified statement-unit node. **Prefer the
statement-unit nodes** (`semunit:*StatementUnit`); only drop to the OBI chain for numeric measurement
*values* (see below).

## Real-world entities

- **Species occurrence** — `base:Plant/<Sp>_<Gar>_<Year>`, typed `dwc:Occurrence`. The central node:
  one plant, one garden, one year. `rdfs:label` is the **scientific (Latin) name** (e.g.
  `"Tulipa sylvestris"`). Links: `dcterms:identifier` → its `dwc:Taxon`; `obo:RO_locatedIn` → a
  Wikidata garden URI; `obo:RO_hasQuality` → quality nodes; `obo:OBI_isSpecifiedInputOf` → observing
  processes.
- **Organism** — `base:Organism/<Sp>_<Gar>`, typed `dwc:Organism`. The species-at-a-garden across all
  years; `rdfs:label` = Latin name; `dcterms:identifier` → its yearly `dwc:Occurrence` nodes. Usually
  you query `dwc:Occurrence` directly, not `dwc:Organism`.
- **Taxon** — URI is the GBIF page `https://www.gbif.org/species/<id>`, typed `dwc:Taxon`. Carries the
  **common names** as language-tagged `rdfs:label`s (`@de`, `@en`) plus the Latin name (untagged), and
  `dwc:taxonRank`, `dwc:taxonID`, `dwc:parentNameUsageID` (→ parent taxon), an IUCN status
  (`wdt:P141`), and an image URL (`schema:url`).
- **Garden** — typed `obo:ENVO_BotanicalGarden` (15). `rdfs:label` = garden name; `geo:lat`/`geo:long`
  = coordinates; `obo:RO_locatedIn` → Wikidata *city*. **City** — typed `schema:City` (15), only an
  `rdfs:label` (e.g. `"Jena"`, `"Halle (Saale)"`, `"Vienna"`).

## How an observation is stored (the happy path)

For each occurrence there is one statement-unit node per phenophase. **These are the nodes to query.**
Each carries: `semunit:hasSemanticUnitSubject` → the `dwc:Occurrence`; `obo:BFO_occursIn` → a
`semunit:geoIndexStatementUnit` (the garden); a readable `rdfs:label`; and, for date phenophases,
`time:hasTime/time:inDateTime` → a `time:DateTimeDescription` with `time:dayOfYear` and `time:year`
(both **`xsd:int`**).

Phenophase statement-unit types (one instance per species·garden·year):

| Statement unit | Meaning | Value lives in |
|---|---|---|
| `semunit:firstFlowerStatementUnit` | first flower / pollen-releasing inflorescence | date (`dayOfYear`) |
| `semunit:lastFlowerStatementUnit` | last flower / open inflorescence | date (`dayOfYear`) |
| `semunit:leafUnfStatementUnit` | leaf unfolding (mature true leaf) | date (`dayOfYear`) |
| `semunit:senOnStatementUnit` | senescence onset (senesced true leaf) | date (`dayOfYear`) |
| `semunit:floweringDurationStatementUnit` | flowering duration (days) | number (see below) |
| `semunit:GSLStatementUnit` | growing-season length (days) | number (see below) |

The **garden** node reached by `obo:BFO_occursIn` is a `semunit:geoIndexStatementUnit` whose
`rdfs:label` reads e.g. `"Botanischer Garten Jena located in city Jena has lat 50.9311 and long
11.5861"` and whose `semunit:hasSemanticUnitSubject` is the Wikidata garden URI. Filter a garden by
`FILTER(CONTAINS(?gardenLabel, "Jena"))` on that label.

## Verified query patterns

**First-flower day of a species, per garden, in a year** (also works for last flower / leaf unfolding /
senescence — just swap the statement-unit type):
```sparql
PREFIX semunit: <http://example.com/semunit/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX obo: <http://purl.obolibrary.org/obo/>
SELECT ?occ ?gardenLabel ?dayOfYear WHERE {
  ?u a semunit:firstFlowerStatementUnit ;
     semunit:hasSemanticUnitSubject ?occ ;
     obo:BFO_occursIn ?g ;
     time:hasTime/time:inDateTime ?dtd .
  ?occ rdfs:label "Tulipa sylvestris" .
  ?g rdfs:label ?gardenLabel .
  ?dtd time:dayOfYear ?dayOfYear ; time:year ?year .
  FILTER(?year = 2024)
} LIMIT 200
```

**Top-N species by earliest average first-flower day** (aggregate, no LIMIT trap):
```sparql
PREFIX semunit: <http://example.com/semunit/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?species (AVG(?doy) AS ?avgDay) WHERE {
  ?u a semunit:firstFlowerStatementUnit ;
     semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime ?dtd .
  ?occ rdfs:label ?species .
  ?dtd time:dayOfYear ?doy .
} GROUP BY ?species ORDER BY ?avgDay LIMIT 5
```

**Numeric measurement value (flowering duration / growing-season length).** The statement-unit only
states the number in its label; for a structured value use the typed quality. The quality type is
`base:floweringDuration` or `base:growingSeasonLength`; the value is `xsd:integer`:
```sparql
PREFIX dwc: <http://rs.tdwg.org/dwc/terms/>
PREFIX obo: <http://purl.obolibrary.org/obo/>
PREFIX base: <http://example.com/base/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?occ ?duration WHERE {
  ?occ a dwc:Occurrence ; rdfs:label "Dactylis glomerata" ;
       obo:RO_hasQuality ?q .
  ?q a base:floweringDuration .
  ?datum obo:IAO_isQualityMeasurementOf ?q ; obo:OBI_hasValueSpecification ?spec .
  ?spec obo:IAO_hasMeasurementValue ?duration .
} LIMIT 200
```
A duration/GSL has **no own date**. To restrict it to a year, join a dated statement unit on the same
`?occ` and filter its `time:year` (e.g. add the `firstFlowerStatementUnit … time:year ?year` block and
`FILTER(?year = 2024)`).

**Common name → occurrences** (common names live on the Taxon, Latin name on the Occurrence):
```sparql
PREFIX dwc: <http://rs.tdwg.org/dwc/terms/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?occ ?species WHERE {
  ?taxon a dwc:Taxon ; rdfs:label "Echter Eibisch"@de .
  ?occ a dwc:Occurrence ; dcterms:identifier ?taxon ; rdfs:label ?species .
} LIMIT 200
```

## Entity resolution on this graph

- **Species:** if the user gives a scientific name, match it directly on `?occ rdfs:label "<Latin>"`
  (occurrence labels are exact Latin names). If they give a **common name** (German/English) or a
  possibly-misspelled name, call `resolve_entity` with `type` `dwc:Taxon`, then join occurrences via
  `?occ dcterms:identifier ?taxon`. `resolve_entity` indexes `dwc:Organism`, `dwc:Taxon`,
  `schema:City`, `obo:ENVO_BotanicalGarden`.
- **Gardens / cities:** there are only 15. Filter via the `geoIndexStatementUnit` label
  (`CONTAINS(?gardenLabel, "Jena")`) or `resolve_entity` with `type` `schema:City` /
  `obo:ENVO_BotanicalGarden`.
- Do not `resolve_entity` for a plain scientific name that can match an occurrence label directly.

## KG-specific clarification cases

- A bare phenophase word ("blooming", "flowering") that could mean *first flower*, *last flower* or
  *flowering duration* — ask which.
- A location given as a country or region rather than one of the 15 gardens/cities — ask which garden,
  or aggregate across all.
- A "when did X flower" question without a year, when the answer differs across 2019–2024 — offer to
  report per year or averaged.

## Administrator notes

<!-- ADMIN: add any extra domain context, caveats, or preferred phrasing for this KG here. -->
(none)
