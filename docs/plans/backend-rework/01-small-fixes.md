# 01: Small fixes

**Depends on:** nothing · **Area:** backend

## Goal

Clear the unrelated findings from the plan (section 10) before the rework starts.

## Changes

- `util/sparql_utils.py`, `validate_query()`: match the forbidden keywords
  (`INSERT`, `DELETE`, `CONSTRUCT`, `DROP`) as whole words and case-insensitively instead of as
  case-sensitive substrings. Today `?insertion` or a label like "Constructa" is rejected, while a
  lowercase `insert data` passes. A keyword directly preceded by `?`, `$`, `:` or a word character
  is a variable or prefixed name and must pass.
- `util/config.py`: new setting `sparql_timeout: float = 30.0`. Use it for the shared
  `httpx.AsyncClient` in `main.py` (today a hard-coded `10.0`) and as the `SparqlService` timeout
  (today a second hard-coded `10.0` default in the constructor).
  `lucene_setup.py` keeps its own 60 s (index builds take longer than queries).
- `.env.example`: add `SPARQL_TIMEOUT`.
- `SparqlService.health_check()` gets its own fixed 5 s timeout (like the LLM health check)
  instead of `self.timeout`. Otherwise `/health`, which the frontend polls, would hang for 30 s
  when GraphDB is down.

## Out of scope

- `SparqlService.aclose()` stays (used by `lucene_setup.py`).

## Tests

- `tests/test_util/test_sparql_utils.py`: variable `?insertion`, literal containing "Constructa"
  inside a longer word, lowercase `insert data` rejected, `?delete` accepted.
- `tests/conftest.py`: add `sparql_timeout` to `settings_stub`.
- `test_sparql_service.py`: the health check uses the short timeout, not `sparql_timeout`.

## Docs

- `docs/configuration.md`: `SPARQL_TIMEOUT`.
