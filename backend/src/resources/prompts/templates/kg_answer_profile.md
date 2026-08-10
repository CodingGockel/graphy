<!--
  PER-KG ANSWER PROFILE for the phenology knowledge graph. Graph-specific guidance for
  presenting results: terminology, value interpretation, and label/URI clean-up.
  Verified against the live endpoint. When migrating to another graph, replace this file.
-->
# Domain: presenting phenology results

The data is about **plant phenology** in botanical gardens (2019–2024): when species flower, unfold
leaves, and senesce. Present results the way a botanist or curious visitor would expect.

## Interpreting values

- **Day-of-year** (the flowering/leaf dates) is an integer 1–366. Convert it to a calendar date for
  the stated year (leap-year aware) and show both, e.g. day 87 in 2024 → "27 March 2024 (day 87)".
- **Flowering duration** and **growing-season length** are counts of **days** — say "X days".
- **Coordinates** are decimal degrees: present as "latitude / longitude".

## Terminology (internal → reader-friendly)

- *first flower / pollen-releasing inflorescence present* → "first flowering"
- *last flower / open inflorescence present* → "end of flowering"
- *leaf unfolding / mature true leaf present* → "leaf unfolding"
- *senescence onset / senesced true leaf present* → "onset of senescence (leaf colouring/fall)"
- *flowering duration* → "flowering duration"
- *growing-season length* → "growing-season length"

## Related information you can offer

When inviting the user to explore further, suggest only from these categories — all of them exist in
this graph:
- **For a species:** other phenophases (first flowering, end of flowering, leaf unfolding, onset of
  senescence), flowering duration, growing-season length, IUCN Red List status, taxonomic
  family/genus/rank, which of the 15 gardens it grows in, and how values vary across years or gardens.
- **For a garden:** coordinates, city/country, number of species recorded, earliest/latest flowering,
  and comparison with other gardens.
- **Cross-cutting:** year-to-year trends (2019–2024) and garden-vs-garden comparisons.

## Labels and identifiers

- **Garden labels are verbose** — e.g. "Botanischer Garten Jena located in city Jena has lat 50.9311
  and long 11.5861". Show only the garden name (or the city), not the lat/long sentence.
- **Species:** the scientific (Latin) name is the primary identifier; include a common name if the
  data provides one.
- If a result contains a raw **Wikidata garden URI** instead of a label, map it via the table below.

| Wikidata URI ends with | Garden / city |
|---|---|
| Q317714 | Botanical Garden Jena (Jena) |
| Q894645 | Halle-Wittenberg University Botanical Garden (Halle) |
| Q677602 | Botanical Garden of the University of Vienna (Vienna) |
| Q321565 | Botanical Garden Potsdam (Potsdam) |
| Q195786 | Prague Botanical Garden (Prague) |
| Q163255 | Botanic Garden & Botanical Museum Berlin (Berlin) |
| Q319334 | Botanical Garden Frankfurt am Main (Frankfurt) |
| Q323954 | Leipzig Botanical Garden (Leipzig) |
| Q613250 | Loki Schmidt Garden (Hamburg) |
| Q4948485 | Botanical Garden of the University of Tübingen (Tübingen) |
| Q4998 | Ringve Botanical Garden (Trondheim) |
| Q4095115 | Botanical Garden PetrSU (Petrozavodsk) |
| Q54681445 | Alpinum Schatzalp (Davos) |
| Q5926368 | Atlantic Botanical Garden (Gijón) |
| Q17495732 | Jawaharlal Nehru Memorial Botanical Garden (Srinagar) |
