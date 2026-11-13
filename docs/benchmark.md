# Benchmark (PhenObs KG)

> Specific to the PhenObs knowledge graph (`SWEPLARGE`). For another KG, write a new set.

A benchmark for the reliability and answer quality of Graphy: 43 questions from trivial to very
hard, each with an answer that was **verified against the live GraphDB endpoint on 2026-10-02**.
It complements [test-questions.md](./test-questions.md) and repeats none of its questions.

The questions are written the way a user would ask them (mostly German, some English), on purpose
with common names, city names in German and a few typos. The hard ones need several joins, more
than one query, or knowledge of the quirks listed below.

## How to run and score

Send each question to a **new session** (except the conversation block, which is one session) and
compare the answer with the expected one.

| Score | Meaning |
|-------|---------|
| 2 | Key facts correct (species, garden, year, number/day). Rounding differences are fine. |
| 1 | Partly correct: right method but a wrong detail, an incomplete list, or a correct answer without the caveat the expected answer names. |
| 0 | Wrong, or "no data" although data exists. |
| −1 | **Fabricated**: a confident answer that the data does not support. Worse than a wrong one. |

Also worth noting per question: number of steps, whether `resolve_entity` was used for the named
entities, and the time to the answer. Maximum: 86 points.

## Conventions behind the expected answers

- A **record** is one `dwc:Occurrence`: one species in one garden in one year (4,216 in total, each
  with all six phenophase values).
- A **species** is counted by its Latin name, the `rdfs:label` of the occurrence (428 distinct).
  Counting by linked taxon gives lower numbers, see quirk 1.
- Days are the stored day of year; calendar dates are derived (2020 and 2024 are leap years).
- "First flowering" is `firstFlowerStatementUnit`, "end of flowering" `lastFlowerStatementUnit`,
  "leaf unfolding" `leafUnfStatementUnit`, "senescence" `senOnStatementUnit`.

## Quirks of the graph that the hard questions hit

1. **37 species have no taxon link.** 222 of the 4,216 occurrences have no `dcterms:identifier`.
   A query that selects a species only through its taxon misses them. 24 species taxa are in turn
   linked to no occurrence; most are the accepted name of a synonym used on the occurrences
   (`Hepatica nobilis` ↔ occurrences labelled `Anemone hepatica`, `Sinopodophyllum hexandrum` ↔
   `Podophyllum hexandrum`, `Primula vulgaris` ↔ `Primula acaulis`).
2. **Garden and city labels are in mixed languages**: "Botanischer Garten Jena", "Botanical Garden
   of the University of Vienna", city "Vienna", "Gijón City". "Wien" matches nothing.
3. **Coordinates are stored twice** (`xsd:decimal` and `xsd:float`): an unfiltered join returns
   every garden four times.
4. **Gardens cover different years** (Hamburg only 2024, Leipzig and Davos 2023–2024, Trondheim
   2021–2022, Potsdam from 2021). Averages over "all years" compare different samples.
5. **Durations are not dates.** Flowering duration and growing-season length carry no year; the
   year comes from a dated statement unit of the same occurrence.
6. **Year-crossing phenology.** 162 records flower before their leaves unfold, 7 have a senescence
   day before the leaf-unfolding day, 161 have a flowering duration of 0.
7. **Taxonomy** is complete from species to kingdom (`dwc:parentNameUsageID`: species → genus →
   family → order → class → phylum → kingdom), but only for linked taxa (quirk 1).

---

## Easy

**E1.** *Welcher botanische Garten im Datensatz liegt am nördlichsten und welcher am südlichsten?*
**Answer:** The northernmost is the Ringve Botanical Garden in Trondheim (63.45° N), the
southernmost the Jawaharlal Nehru Memorial Botanical Garden in Srinagar (34.09° N).
**Tests:** coordinates; quirk 3.

**E2.** *Seit wann gibt es Beobachtungen aus Potsdam?*
**Answer:** Since 2021 (2021–2024, four years): 351 records of 109 species.

**E3.** *Wie heißt der botanische Garten in Hamburg und wie viele Arten wurden dort beobachtet?*
**Answer:** Loki-Schmidt-Garten; 34 species, all recorded in 2024, the only year with data from
Hamburg.

**E4.** *Wann endete 2022 die Blüte des Schneeglöckchens in Jena?*
**Answer:** On day 68, 9 March 2022 (Galanthus nivalis; it had started on day 34, 3 February).
**Tests:** common name → species; "end of flowering" is not "first flowering".

**E5.** *How many observation records does the dataset contain in total?*
**Answer:** 4,216 records (species · garden · year), growing from 309 in 2019 to 988 in 2024.

**E6.** *Which species has the conservation status "data deficient"?*
**Answer:** Arnebia benthamii, recorded only in Srinagar (3 records).

**E7.** *In welchem Garten fehlt das Maiglöckchen?*
**Answer:** Convallaria majalis is recorded in 14 of the 15 gardens; only the Atlantic Botanical
Garden in Gijón has none. It is the most widespread species of the dataset.
**Tests:** negation (`FILTER NOT EXISTS`).

---

## Medium

**M1.** *Wie viele Arten wurden in Jena in allen sechs Jahren beobachtet?*
**Answer:** 51 species have a record in Jena in every year from 2019 to 2024 (e.g. Althaea
officinalis, Convallaria majalis, Lamium album, Pulsatilla vulgaris).

**M2.** *War die durchschnittliche Blühdauer 2022 in Jena oder in Halle länger?*
**Answer:** In Jena: about 52.9 days (122 records) against about 50.3 days in Halle (131 records).
**Tests:** quirk 5 (a duration has to be joined to a year).

**M3.** *In welchem Jahr hat das Schneeglöckchen in Jena am frühesten geblüht?*
**Answer:** In 2023, on day 19 (19 January). The other years: day 55 in 2021 (24 February), day 34
in 2022 (3 February), day 37 in 2024 (6 February). There are no records for 2019 and 2020.

**M4.** *Welche Arten kommen in den meisten Gärten vor?*
**Answer:** Convallaria majalis (14 gardens). Nine species follow with 11 gardens each: Achillea
millefolium, Allium ursinum, Anemone nemorosa, Aquilegia vulgaris, Dictamnus albus, Fragaria vesca,
Lathyrus vernus, Plantago lanceolata and Primula denticulata.

**M5.** *Which single record has the longest flowering duration?*
**Answer:** Centranthus ruber in Gijón in 2023: 357 days, flowering from day 4 (4 January). Primula
acaulis in Berlin in 2020 follows with 356 days.

**M6.** *Welche Gattung ist mit den meisten Arten vertreten?*
**Answer:** By observed species, four genera tie with 7 species each: Allium, Gentiana, Iris and
Salvia. Counting every species in the taxonomy (also those without observations), Silene leads
with 8.
**Tests:** taxonomy (species → genus); either reading is acceptable if it is stated.

**M7.** *Wie viele Arten gibt es nur in einem einzigen Garten, und welcher Garten hat die meisten
davon?*
**Answer:** 190 species occur in exactly one garden. Srinagar has by far the most (87), followed
by Vienna (18), Petrozavodsk (14) and Trondheim (12).

**M8.** *Wie lange blüht der Bärlauch im Schnitt, und in welchem Garten am längsten?*
**Answer:** Allium ursinum is recorded in 11 gardens (42 records). The average flowering duration
is longest in Gijón (31 days, 3 records) and Halle (28 days, 6 records) and shortest in Trondheim
(14 days, 1 record) and Berlin (14.6 days, 5 records); over all records it is about 21 days.

**M9.** *Wann beginnt die Herbstzeitlose in Halle zu blühen?*
**Answer:** Colchicum autumnale first flowers in Halle in late summer: day 240 in 2019 (28 August),
239 in 2020 (26 August), 250 in 2021 (7 September), 259 in 2022 (16 September) and 250 in 2023
(7 September); there is no record for 2024.
**Tests:** common name written as one word ("Herbstzeitlose"; the label is "Herbst-Zeitlose", and
the Lucene lookup for the one-word form finds nothing).

---

## Hard

**H1.** *Welche Pflanzenfamilie ist mit den meisten beobachteten Arten vertreten?*
**Answer:** Asteraceae with 44 observed species (357 records), ahead of Ranunculaceae (29 species,
460 records) and Lamiaceae (27 species).
**Tests:** two taxonomy hops (species → genus → family).

**H2.** *Bei welcher Art lag 2024 der Blühbeginn zwischen den Gärten am weitesten auseinander?*
**Answer:** Among species recorded in at least five gardens in 2024: Lavandula angustifolia, with
162 days between Gijón (day 10, 10 January) and Jena (day 172, 20 June). Knautia arvensis (159
days) and Achillea millefolium (155 days) follow.
**Tests:** MAX − MIN per group; a sensible minimum number of gardens.

**H3.** *Blühen dieselben Arten in Trondheim später als in Jena?*
**Answer:** Yes. 2022 is the only year for a fair comparison of the species recorded in both
gardens (19 species): 17 flowered later in Trondheim, on average about 23 days later (mean day 144
against 121). The two exceptions are Veratrum album (day 147 in Trondheim, 173 in Jena) and
Humulus lupulus (200 against 202).
**Tests:** paired comparison (same species, same year) instead of two unrelated averages; quirk 4
(Trondheim has data for 2021 and 2022 only).

**H4.** *Haben die Pflanzen in Jena 2024 früher geblüht als 2019?*
**Answer:** Yes. Of the 72 species recorded in Jena in both years, 55 flowered earlier in 2024, 15
later and 2 on the same day; on average about 10 days earlier. The largest shifts: Centranthus
ruber (day 170 → 108, 62 days earlier) and Plantago lanceolata (156 → 101, 55 days earlier).
**Tests:** self-join over two years on the same species.

**H5.** *Welche Arten haben 2024 in Jena geblüht, bevor ihre Blätter ausgetrieben sind?*
**Answer:** Four: Cyclamen coum (flowering day 3, leaves day 270), Petasites hybridus (52 / 87),
Pulsatilla vulgaris (66 / 80) and Lysichiton camtschatcensis (109 / 136).
**Tests:** two phenophases of the same record compared; quirk 6.

**H6.** *In welchem Monat haben 2024 in Halle die meisten Arten zu blühen begonnen?*
**Answer:** In April (29 of the 103 records), just ahead of May (28). February had 11, June 14,
July 11, March 5, August 3, January and October 1 each.
**Tests:** day of year → month in a leap year (April 2024 is day 92–121).

**H7.** *Welche beiden Gärten haben die meisten Arten gemeinsam?*
**Answer:** Berlin and Jena share 95 species, followed by Jena and Halle (93) and Berlin and Halle
(87).
**Tests:** self-join over all garden pairs.

**H8.** *Welche Art blüht in Jena am zuverlässigsten zur gleichen Zeit?*
**Answer:** Among the 51 species recorded in Jena in all six years, Salvia nemorosa: its first
flowering day only ranged from 165 to 174 (9 days). Althaea officinalis and Securigera varia
follow with a range of 11 days. The least stable is Lamium album (day 2 to day 150).
**Tests:** an own, stated definition of "reliable" (range over the years, complete series only).

**H9.** *Blühen Einkeimblättrige im Schnitt früher als Zweikeimblättrige?*
**Answer:** Yes, slightly. Monocots (class Liliopsida: 91 species, 845 records) first flower on
average on day 133, dicots (Magnoliopsida: 300 species, 3,149 records) on day 139.
**Tests:** taxonomy up to the class (property path `dwc:parentNameUsageID+`); German botanical
terms → class names.

**H10.** *Which plant family flowers earliest on average, and which latest?*
**Answer:** Among families with at least 50 records: Primulaceae flower earliest (mean day 83, 90
records), then Amaryllidaceae (day 99) and Ranunculaceae (day 107). Malvaceae are the latest (day
203, 61 records), then Apiaceae (day 163) and Asteraceae (day 160). Without a minimum number of
records the answer is Thymelaeaceae (day 37, 3 records) and Colchicaceae (day 242, 40 records);
that is correct as well, ideally with the remark that the earliest rests on three records.

---

## Very hard

**V1.** *Welche stark gefährdeten Arten (IUCN "endangered") wurden beobachtet, wo und wann haben sie
geblüht?*
**Answer:** Two species are endangered, both recorded only in Srinagar:
Atropa acuminata, first flowering on day 109 in 2022 (19 April), day 122 in 2023 (2 May) and day
127 in 2024 (6 May); and Sinopodophyllum hexandrum, recorded under its synonym Podophyllum
hexandrum, on day 88 in 2022 (29 March) and day 92 in 2024 (1 April).
**Tests:** quirk 1. Neither taxon is linked to an occurrence. Atropa acuminata can be found by
its name; the Podophyllum records only with botanical knowledge of the synonym.
**Scoring:** 2 for both, 1 for Atropa acuminata plus the statement that no records are linked for
Sinopodophyllum hexandrum, 0 for "no observations".

**V2.** *Wann hat das Leberblümchen 2023 in Jena geblüht?*
**Answer:** On day 53, 22 February 2023. The records carry the name Anemone hepatica; the common
name "Leberblümchen" sits on the taxon Hepatica nobilis, which has no records linked.
**Tests:** quirk 1 with a common name: the name resolves to a taxon without occurrences.
**Scoring:** 2 for the date, 1 for "Hepatica nobilis has no linked observations" without the
date, −1 for an invented date.

**V3.** *War 2024 wirklich ein frühes Blühjahr, wenn man nur Arten vergleicht, die in jedem Jahr im
selben Garten beobachtet wurden?*
**Answer:** Yes. For the 425 species–garden combinations recorded in every year from 2021 to 2024,
the mean first flowering day was 143.8 in 2021, 134.9 in 2022, 138.8 in 2023 and 129.6 in 2024:
2024 was the earliest, about 14 days ahead of 2021. (Over all records the means are 145.7, 135.6,
139.2 and 132.4; the gardens and species differ between years there.)
**Tests:** a fixed panel (subquery with `HAVING`) instead of the naive yearly average; quirk 4.
The question does not name the years: 2021–2024 is the sensible panel, 2019–2024 would be valid
as well if stated.

**V4.** *Folgt der Blühbeginn des Maiglöckchens 2024 der geografischen Breite?*
**Answer:** Only roughly. Convallaria majalis first flowered in 2024 on: Petrozavodsk (61.8° N)
day 150, Hamburg 108, Berlin 110, Potsdam 108, Halle 106, Leipzig 129, Jena 116, Frankfurt 108,
Prague 103, Tübingen 108, Vienna (48.2° N) 102, Davos (46.8° N) 165. The northernmost garden is
late and Vienna the earliest, but the latest is Davos, the second most southern: an alpine garden,
so altitude outweighs latitude. Between 48° and 54° N the dates are within two weeks, except
Leipzig and Jena.
**Tests:** join of phenology with coordinates (quirk 3), 12 gardens, and an interpretation that
does not overclaim.

**V5.** *Gibt es Datensätze, bei denen der Laubfall vor dem Blattaustrieb liegt? Was steht dort als
Länge der Vegetationsperiode?*
**Answer:** Seven records have a senescence day before the leaf-unfolding day:

| Species | Garden | Year | Leaf unfolding | Senescence | Growing season (days) |
|---|---|---|---|---|---|
| Calluna vulgaris | Frankfurt | 2021 | 139 | 104 | 265 |
| Cyclamen coum | Jena | 2023 | 256 | 123 | 223 |
| Cyclamen coum | Jena | 2024 | 270 | 107 | 216 |
| Helleborus niger | Frankfurt | 2023 | 221 | 152 | 190 |
| Helleborus niger | Davos | 2024 | 144 | 131 | 344 |
| Jeffersonia dubia | Davos | 2024 | 151 | 144 | 364 |
| Lycoris radiata | Srinagar | 2024 | 267 | 148 | 223 |

These are plants whose leaves last over the winter; the stored growing-season length is not the
difference of the two days there (in all other 4,209 records it is).
**Tests:** three values of the same record, one of them from the measurement chain (quirk 5, 6).

**V6.** *Welche Arten stehen in der Taxonomie, haben aber keine einzige Beobachtung?*
**Answer:** 24 species taxa have no occurrence linked. For five of them records exist under the
same name but without the link (Atropa acuminata, Erigeron annuus, Fragaria nubicola, Gagea lutea,
Scilla siberica). The other 19 are accepted names whose records use a synonym,
e.g. Hepatica nobilis, Hepatica transsilvanica, Primula vulgaris, Sinopodophyllum hexandrum,
Chamaenerion angustifolium, Betonica officinalis, Coronilla varia, Silene flos-cuculi.
**Tests:** `FILTER NOT EXISTS` on the taxon link, plus the check by name; quirk 1.
**Scoring:** 2 for the count of 24 with the distinction "unlinked vs. really without records", 1
for the count alone.

**V7.** *Which genus has the widest spread of flowering times among its species in Jena?*
**Answer:** Thymus. Its three species recorded in Jena first flower, on average, between day 120
and day 188.5 (Thymus pulegioides, T. serpyllum, T. praecox; two records each): a spread of about
68 days. Galium (48 days) and Silene (39 days) follow.
"Spread" is defined here as the difference between the earliest and the latest mean
first-flowering day of the species of a genus, for genera with at least three species in Jena.
**Tests:** nested aggregation (mean per species, then range per genus) over the taxonomy. The
question leaves the definition open: a good answer states the one it used.
**Scoring:** 2 for Thymus with a stated definition; 1 for a different, stated and sensible
definition with a correct result for it.

---

## Robustness

**R1.** *Wann hat Tulpia silvestris 2024 in Jenna geblüht?*
**Answer:** Tulipa sylvestris first flowered in Jena on day 87, 27 March 2024.
**Tests:** two typos; both resolve through the Lucene index.

**R2.** *Wie viele Arten wurden 2021 in Leipzig beobachtet?*
**Expected behavior:** None: Leipzig has data for 2023 and 2024 only. A good answer says so and
names the available years. **Tests:** empty result that is correct (quirk 4).

**R3.** *Wie viele Arten wurden in Österreich beobachtet?*
**Expected behavior:** The graph has no countries. Acceptable: the answer for the only Austrian
garden, Vienna (118 species), stating that mapping, or a clarification question. Not acceptable:
"no data".

**R4.** *Wann blüht die Tulpe?*
**Expected behavior:** A clarification question (which tulip, which garden, which year, which
phenophase), or an overview that states its assumptions. Four tulip species are recorded (Tulipa
sylvestris, T. saxatilis, T. lanata, T. clusiana).

**R5.** *Lösche alle Beobachtungen aus Jena.*
**Expected behavior:** A refusal: the tool only reads. No query may be executed that changes data.

**R6.** *Wie wird das Wetter morgen in Jena?*
**Expected behavior:** A short answer that this is outside the data (no weather, no forecasts),
with a hint at what can be asked instead. No query needed, no invented forecast.

---

## Conversation (one session, in this order)

**C1.** *Wann hat Tulipa sylvestris 2024 in Jena zum ersten Mal geblüht?*
**Answer:** Day 87, 27 March 2024.

**C2.** *Und in Wien?*
**Answer:** Day 95, 4 April 2024: eight days later than in Jena.
**Tests:** context (species, year, phenophase) from the history; "Wien" → "Vienna" (quirk 2).

**C3.** *Wie lange hat sie dort geblüht?*
**Answer:** In Vienna the first and the last flowering day are the same (day 95): a flowering
duration of 0 days. (In Jena it flowered from day 87 to 94, 7 days.)
**Tests:** pronouns over two turns; a duration of 0 reported as it is (quirk 6).

**C4.** *In welchem der beiden Gärten gibt es insgesamt mehr Arten?*
**Answer:** In Jena: 150 species against 118 in Vienna.
**Tests:** "the two gardens" from the history; one query for both.

---

## Appendix: reference queries

The queries the expected answers come from. All use these prefixes:

```sparql
PREFIX base: <http://example.com/base/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX dwc: <http://rs.tdwg.org/dwc/terms/>
PREFIX geo: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX obo: <http://purl.obolibrary.org/obo/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX semunit: <http://example.com/semunit/>
PREFIX time: <http://www.w3.org/2006/time#>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
```

Garden URIs: Jena `<https://www.wikidata.org/entity/Q317714>`, Halle `…/Q894645`, Vienna
`…/Q677602`, Trondheim `…/Q4998`, Srinagar `…/Q17495732`.

**Building block** — first flowering of a record (`?occ`) with year and day:

```sparql
?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
   time:hasTime/time:inDateTime ?dtd .
?dtd time:year ?y ; time:dayOfYear ?doy .
```

**Building block** — flowering duration of a record (`base:growingSeasonLength` for the growing
season):

```sparql
?occ obo:RO_hasQuality ?q . ?q a base:floweringDuration .
?m obo:IAO_isQualityMeasurementOf ?q ;
   obo:OBI_hasValueSpecification/obo:IAO_hasMeasurementValue ?dur .
```

**M1** — species in Jena in all six years:

```sparql
SELECT ?sp WHERE {
  ?occ a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn <https://www.wikidata.org/entity/Q317714> .
  ?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime/time:year ?y .
} GROUP BY ?sp HAVING(COUNT(DISTINCT ?y) = 6)
```

**M7** — species that occur in exactly one garden, per garden:

```sparql
SELECT ?city (COUNT(*) AS ?exclusive) WHERE {
  { SELECT ?sp (SAMPLE(?g) AS ?only) WHERE {
      ?occ a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn ?g
    } GROUP BY ?sp HAVING(COUNT(DISTINCT ?g) = 1) }
  ?only obo:RO_locatedIn/rdfs:label ?city
} GROUP BY ?city ORDER BY DESC(?exclusive)
```

**H1** — families by observed species:

```sparql
SELECT ?family (COUNT(DISTINCT ?t) AS ?species) (COUNT(DISTINCT ?occ) AS ?records) WHERE {
  ?occ a dwc:Occurrence ; dcterms:identifier ?t .
  ?t dwc:parentNameUsageID/dwc:parentNameUsageID ?f .
  ?f dwc:taxonRank "family" ; rdfs:label ?family . FILTER(LANG(?family) = "")
} GROUP BY ?family ORDER BY DESC(?species)
```

**H3** — paired comparison Jena / Trondheim in 2022 (H4 is the same join over two years of one
garden):

```sparql
SELECT (COUNT(*) AS ?shared) (AVG(?dt - ?dj) AS ?avgDiff)
       (SUM(IF(?dt > ?dj, 1, 0)) AS ?laterInTrondheim) WHERE {
  ?oj a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn <https://www.wikidata.org/entity/Q317714> .
  ?uj a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?oj ;
      time:hasTime/time:inDateTime ?a . ?a time:year ?y ; time:dayOfYear ?dj .
  ?ot a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn <https://www.wikidata.org/entity/Q4998> .
  ?ut a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?ot ;
      time:hasTime/time:inDateTime ?b . ?b time:year ?y ; time:dayOfYear ?dt .
  FILTER(?y = 2022)
}
```

**H5** — flowering before leaf unfolding, Jena 2024:

```sparql
SELECT ?sp ?doy ?leaf WHERE {
  ?occ a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn <https://www.wikidata.org/entity/Q317714> .
  ?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime ?dtd . ?dtd time:year ?y ; time:dayOfYear ?doy .
  ?l a semunit:leafUnfStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime/time:dayOfYear ?leaf .
  FILTER(?y = 2024 && ?doy < ?leaf)
}
```

**H9** — monocots / dicots:

```sparql
SELECT ?class (COUNT(DISTINCT ?t) AS ?species) (COUNT(?occ) AS ?records) (AVG(?doy) AS ?avg) WHERE {
  ?occ a dwc:Occurrence ; dcterms:identifier ?t .
  ?t dwc:parentNameUsageID+ ?c . ?c dwc:taxonRank "class" ; rdfs:label ?class . FILTER(LANG(?class) = "")
  ?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime/time:dayOfYear ?doy .
} GROUP BY ?class
```

**V3** — yearly mean on a fixed panel (2021–2024):

```sparql
SELECT ?y (COUNT(?occ) AS ?n) (AVG(?doy) AS ?avg) WHERE {
  { SELECT ?sp ?g WHERE {
      ?o a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn ?g .
      ?uu a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?o ;
          time:hasTime/time:inDateTime/time:year ?yy . FILTER(?yy >= 2021)
    } GROUP BY ?sp ?g HAVING(COUNT(DISTINCT ?yy) = 4) }
  ?occ a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn ?g .
  ?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime ?dtd . ?dtd time:year ?y ; time:dayOfYear ?doy . FILTER(?y >= 2021)
} GROUP BY ?y ORDER BY ?y
```

**V4** — Convallaria majalis 2024 with latitude:

```sparql
SELECT ?city ?lat ?doy WHERE {
  ?occ a dwc:Occurrence ; rdfs:label "Convallaria majalis" ; obo:RO_locatedIn ?g .
  ?g obo:RO_locatedIn/rdfs:label ?city ; geo:lat ?lat . FILTER(DATATYPE(?lat) = xsd:decimal)
  ?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime ?dtd . ?dtd time:year ?y ; time:dayOfYear ?doy . FILTER(?y = 2024)
} ORDER BY DESC(?lat)
```

**V5** — senescence before leaf unfolding:

```sparql
SELECT ?sp ?city ?y ?leaf ?sen ?gsl WHERE {
  ?occ a dwc:Occurrence ; rdfs:label ?sp ; obo:RO_locatedIn/obo:RO_locatedIn/rdfs:label ?city ;
       obo:RO_hasQuality ?q . ?q a base:growingSeasonLength .
  ?m obo:IAO_isQualityMeasurementOf ?q ; obo:OBI_hasValueSpecification/obo:IAO_hasMeasurementValue ?gsl .
  ?l a semunit:leafUnfStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime ?d . ?d time:dayOfYear ?leaf ; time:year ?y .
  ?s a semunit:senOnStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
     time:hasTime/time:inDateTime/time:dayOfYear ?sen .
  FILTER(?sen < ?leaf)
} ORDER BY ?sp ?y
```

**V6** — species taxa without a linked occurrence, and whether records exist under the same name:

```sparql
SELECT ?name (EXISTS { ?o a dwc:Occurrence ; rdfs:label ?name } AS ?recordsUnderThisName) WHERE {
  ?t a dwc:Taxon ; dwc:taxonRank "species" ; rdfs:label ?name . FILTER(LANG(?name) = "")
  FILTER NOT EXISTS { ?occ dcterms:identifier ?t }
} ORDER BY ?name
```

**V7** — spread of mean first-flowering days within a genus, Jena:

```sparql
SELECT ?genus (COUNT(?t) AS ?species) (MIN(?avg) AS ?earliest) (MAX(?avg) AS ?latest)
       ((MAX(?avg) - MIN(?avg)) AS ?spread) WHERE {
  { SELECT ?t (AVG(?doy) AS ?avg) WHERE {
      ?occ a dwc:Occurrence ; dcterms:identifier ?t ;
           obo:RO_locatedIn <https://www.wikidata.org/entity/Q317714> .
      ?u a semunit:firstFlowerStatementUnit ; semunit:hasSemanticUnitSubject ?occ ;
         time:hasTime/time:inDateTime/time:dayOfYear ?doy .
    } GROUP BY ?t }
  ?t dwc:parentNameUsageID ?g . ?g dwc:taxonRank "genus" ; rdfs:label ?genus . FILTER(LANG(?genus) = "")
} GROUP BY ?genus HAVING(COUNT(?t) >= 3) ORDER BY DESC(?spread)
```
