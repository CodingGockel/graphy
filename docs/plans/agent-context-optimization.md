# Epic: agent context and answer quality

An idea, not yet a refined plan. It is **separate from the backend rework**
([`backend-rework/`](./backend-rework/README.md)) and starts after it, because it builds on the
`steps` table that the rework introduces.

**Status:** idea, written down 2026-10-01. No tickets yet.

## Goal

Better answers in fewer tool-loop iterations, especially in longer sessions, by treating
**structural knowledge** and **data results** differently in the agent's context.

## Where context is lost today

- **Only text survives between turns.** The history sent to the LLM is the question and answer of
  the last N turns (`_build_history` in `chat_service.py`). Tool calls and their results are gone.
- **Resolved entities are looked up again every turn.** If "Tulipa sylvestris" was resolved with
  `resolve_entity` in turn 1, a follow-up like "and in Leipzig?" starts from scratch.
- **Working query patterns are forgotten.** A join path that worked after two failed attempts is
  guessed again in the next turn.
- **The schema is already there.** `build_prompt.py` writes classes and properties into the system
  prompt. A tool that "extracts the ontology" adds little for PhenObs; it matters for a KG whose
  schema does not fit into the prompt.

## Idea: three layers of context

| Layer | Content | Lifetime | Truncated? |
|-------|---------|----------|------------|
| Static schema | classes, properties, prefixes (system prompt) | per KG | no |
| Session memory | structural findings of this session | per session | no, but bounded in size |
| Data results | SPARQL result sets | per turn, reusable by reference | yes, as today |

The session memory is small, always in context, and never compacted. Data results stay ephemeral.

## Building blocks

Ordered by how I would approach them. Each would become one or more tickets.

1. **Measurement baseline.** Run the questions from `docs/test-questions.md` and record, per
   question, iterations, failed queries and correctness. The `steps` table provides the first two
   for free. Without this, every later change is a guess.
2. **Session memory filled from steps (deterministic).** No new tool, nothing the model has to do:
   - resolved entities (term → URI),
   - the successful queries of the session,
   - errors that led to a corrected query.
   Rendered as a bounded block after the stable system prompt, so the prompt prefix stays
   cacheable.
3. **Schema check before execution.** Predicates and classes that do not exist in the extracted
   schema are fed back to the model as an error without a round trip to GraphDB.
4. **Example retrieval.** Put the most similar verified question–query pairs into the prompt.
   `docs/test-questions.md` already holds such pairs for PhenObs; onboarding a new KG would include
   providing some.
5. **Inspection tool.** Lets the model look up what the schema does not show: the actual values of
   a property, example instances of a class. Its results count as structural and go into the
   session memory automatically.

## Deliberately not planned (for now)

- **A free-form "remember this" tool.** The Blablador models are unreliable enough at tool calling
  that tool calls have to be recovered from text; every additional tool raises the error rate. A
  wrong note would also stay in context for the whole session. Facts derived from real query
  results do not have that problem.
- **Memory across sessions.** Per-session only; anything worth keeping across sessions belongs in
  the KG profile (`kg_profile.md`).

## Open questions

- How large may the session memory get, and what is dropped first when it is full?
- Does the inspection tool pay off for PhenObs, or only for larger KGs?
- How are example pairs maintained per KG (file next to the profile, or a small index)?
- Does the frontend show the session memory (it would fit a later trace panel)?
- How is correctness judged in the baseline: by hand, or against the expected answers in
  `test-questions.md`?

## Related work

From memory, **not yet verified**; check before relying on any of it:

- **SPARQL-LLM** (SIB): retrieves similar verified question–query pairs and validates the generated
  query against the schema before running it.
- **SPINACH** (Stanford, Wikidata) and **GRASP** (Freiburg): give the agent search and inspection
  tools instead of putting the whole schema into the prompt.
- **MemGPT / Letta** and Anthropic's writing on context engineering: a small pinned memory block
  next to a truncated history.
