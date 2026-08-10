# Backend Test Questions

A curated set of natural-language questions for end-to-end testing of the chat pipeline
(NL question → SPARQL → NL answer). Every non–edge-case answer below was **verified against the live
GraphDB endpoint** (`SWEPLARGE`) on 2026-06-16.

**Dataset:** plant phenology in 15 botanical gardens, years **2019–2024**. Phenophases recorded per
species·garden·year: first flowering, end of flowering, leaf unfolding, onset of senescence, plus
flowering duration and growing-season length (in days). Dates are stored as *day of year*; the
expected answers convert them to calendar dates (2024 is a leap year).

How to use: send each question to `POST /api/v1/chat` and compare the bot's answer to the expected
answer. A good run answers correctly in ≤2 SPARQL iterations, with no `<think>` leakage, and asks for
clarification only on the ambiguous cases. Numeric values may differ by small amounts depending on how
the LLM aggregates; the key facts (species, garden, day/date, order of magnitude) should match.

---

## Easy

**1.** *How many botanical gardens are in the dataset, and where are they?*
**Answer:** 15 botanical gardens, in Berlin, Frankfurt, Halle (Saale), Hamburg, Jena, Leipzig,
Potsdam and Tübingen (Germany), Vienna (Austria), Prague (Czechia), Davos (Switzerland), Trondheim
(Norway), Petrozavodsk (Russia), Gijón (Spain) and Srinagar (India).
**Difficulty:** easy

**2.** *Which years does the phenological data cover?*
**Answer:** Six years, from 2019 to 2024.
**Difficulty:** easy

**3.** *What are the geographic coordinates of the botanical garden in Jena?*
**Answer:** Approximately 50.9311° N, 11.5861° E (Botanischer Garten Jena).
**Difficulty:** easy

**4.** *On which day did Tulipa sylvestris first flower in Jena in 2024?*
**Answer:** On day 87 of the year — 27 March 2024.
**Difficulty:** easy

**5.** *How many distinct plant species are recorded?*
**Answer:** 428 distinct species (recorded as 1,317 species-at-garden organisms across the gardens).
**Difficulty:** easy

**6.** *What kind of information does the dataset record about each plant?*
**Answer:** For each species in a given garden and year it records phenological events — first
flowering, end of flowering, leaf unfolding and onset of senescence (each as a date) — plus the
flowering duration and the growing-season length in days. Gardens also have names and coordinates;
species carry scientific and common names.
**Difficulty:** easy

---

## Medium

**7.** *On average, when does Tulipa sylvestris first flower across all gardens in 2024?*
**Answer:** Around day 92 of the year (early April 2024). It is recorded in 7 gardens that year,
ranging from day 87 (27 March, in Jena and Tübingen) to day 95 (4 April, in Halle and Vienna).
**Difficulty:** medium

**8.** *Which five species have the earliest average first-flowering day?*
**Answer:** Bellis perennis (≈ day 6), Adonis amurensis (≈ day 25), Cyclamen coum (≈ day 25),
Daphne laureola (≈ day 37) and Eranthis hyemalis (≈ day 37) — all winter/early-spring bloomers. (Note
some rest on very few observations, e.g. Bellis perennis on 2.)
**Difficulty:** medium

**9.** *In which garden did Tulipa sylvestris first flower earliest in 2024?*
**Answer:** Earliest in Jena and Tübingen, both on day 87 (27 March 2024).
**Difficulty:** medium

**10.** *How long did Dactylis glomerata flower in Halle in 2020?*
**Answer:** 34 days.
**Difficulty:** medium

**11.** *How many first-flowering observations are recorded for 2023?*
**Answer:** 861 first-flowering observations. (The yearly count grows over time: 309 in 2019, 480 in
2020, 723 in 2021, 855 in 2022, 861 in 2023, 988 in 2024.)
**Difficulty:** medium

**12.** *What is the average growing-season length of Dactylis glomerata?*
**Answer:** About 152 days (averaged over 19 records).
**Difficulty:** medium

**13.** *Which species first flowers latest in the year in Jena (2024)?*
**Answer:** Crocus speciosus, on day 283 (≈ 9 October 2024) — an autumn-flowering crocus.
**Difficulty:** medium

**14.** *Compare the first-flowering day of Tulipa sylvestris between Jena and Vienna in 2024.*
**Answer:** It flowered earlier in Jena — day 87 (27 March) — than in Vienna — day 95 (4 April), about
8 days earlier in Jena.
**Difficulty:** medium

---

## Hard

**15.** *Did Dactylis glomerata flower earlier in 2024 than in 2019?*
**Answer:** Yes. Its average first-flowering day was about day 131 (≈ 10 May) in 2024 versus about day
149 (≈ 29 May) in 2019 — roughly 18 days earlier in 2024. (Per-year samples are small, 1–5 records, so
this is indicative rather than statistically strong.)
**Difficulty:** hard

**16.** *When does the common marshmallow first flower on average?*
**Answer:** The common marshmallow is Althaea officinalis. On average it first flowers around day 185
of the year — early July — based on 29 records. (Tests resolving an English common name to the
scientific species.)
**Difficulty:** hard

**17.** *Which species has the longest average flowering duration?*
**Answer:** Among species with at least ~10 records, Lamium album has the longest, averaging about 189
days, followed by Helianthemum nummularium (~174 days) and Centranthus ruber (~167 days).
**Difficulty:** hard

---

## Edge cases (test robustness, not just correctness)

**18.** *On which day did Tulipa sylvestris first flower in 2025?*
**Expected behavior:** No data — the dataset only covers 2019–2024. The bot should report that there
are no records for 2025, **not** invent a date.
**Difficulty:** edge (empty result)

**19.** *When does Welwitschia mirabilis flower in this collection?*
**Expected behavior:** Welwitschia mirabilis is not in the dataset. The bot should report that this
species was not found, rather than fabricate phenology data.
**Difficulty:** edge (entity not present)

**20.** *When do the flowers bloom?*
**Expected behavior:** The question is too vague to answer. The bot should ask a clarifying question —
e.g. which species, which garden, which year, and whether "bloom" means first flowering, end of
flowering or flowering duration — rather than guessing.
**Difficulty:** edge (ambiguous → clarification)

---

## Advanced — cross-garden comparisons & other attributes

**21.** *How many species in the collection are threatened on the IUCN Red List?*
**Answer:** Only a handful. By IUCN status: 1 critically endangered (Gentiana kurroo), 2 endangered
(Atropa acuminata, Sinopodophyllum hexandrum) and 1 vulnerable (Galanthus ikariae); a further 3 are
near threatened (Galanthus nivalis, Tulipa lanata, Pulsatilla vulgaris). The large majority are Least
Concern (52) or Not Evaluated (355).
**Difficulty:** hard

**22.** *Which species in the collection is critically endangered, and when and where does it flower?*
**Answer:** Gentiana kurroo (Kashmir gentian) is critically endangered. It is recorded only at the
Srinagar garden (India) and first flowers in late summer — between roughly day 213 and 242 of the year
(early to late August), e.g. day 225 (≈ 12 August) in 2024.
**Difficulty:** hard

**23.** *Which botanical garden records the most plant species, and which the fewest?*
**Answer:** Jena records the most (150 species), just ahead of Halle (149). The fewest are at the
Atlantic Botanical Garden in Gijón (28), followed by Hamburg (34).
**Difficulty:** hard

**24.** *In which botanical garden do plants first flower earliest on average?*
**Answer:** The Atlantic Botanical Garden in Gijón flowers earliest on average (≈ day 125, early May),
narrowly ahead of Tübingen (≈ day 125) and Leipzig (≈ day 129) — consistent with milder, more southern
or Atlantic climates.
**Difficulty:** hard

**25.** *How many plant species are recorded in both the Jena and the Trondheim gardens?*
**Answer:** 41 species are recorded (with a first-flowering observation) in both Jena and Trondheim.
**Difficulty:** hard

**26.** *Which garden has the longest average growing season?*
**Answer:** Tübingen, with an average growing-season length of about 188 days, ahead of Prague
(≈ 178 days) and Jena (≈ 176 days).
**Difficulty:** hard

**27.** *Rank the gardens by how early Tulipa sylvestris first flowered in 2024.*
**Answer:** Earliest in Jena and Tübingen (day 87, 27 March), then Berlin (day 93, 2 April), then
Potsdam and Frankfurt (day 94, 3 April), and latest in Halle and Vienna (day 95, 4 April).
**Difficulty:** hard

**28.** *When did Tulipa sylvestris unfold its leaves in Jena over the years, and in which year was it
earliest?*
**Answer:** Leaf unfolding in Jena: day 30 (2020), day 55 (2021), day 19 (2022), day 32 (2023) and day
25 (2024). Earliest in 2022 (day 19, ≈ 19 January); latest in 2021 (day 55, ≈ 24 February).
**Difficulty:** hard

**29.** *What is the IUCN Red List status of the snowdrop (Galanthus nivalis)?*
**Answer:** Near Threatened. (Tests common-name resolution combined with the IUCN attribute.)
**Difficulty:** hard

**30.** *How many genera and families does the dataset's taxonomy span?*
**Answer:** The taxonomy covers 415 species-rank taxa across 256 genera and 62 families (and higher
ranks: 30 orders, 2 classes, 1 phylum, 1 kingdom).
**Difficulty:** hard
