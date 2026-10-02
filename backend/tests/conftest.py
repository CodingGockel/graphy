"""Shared fixtures. All external boundaries (OpenAI, httpx/GraphDB, the DB) are
mocked, so the suite runs offline — no VPN, GraphDB, Postgres or API key needed."""
from types import SimpleNamespace

import pytest


@pytest.fixture
def settings_stub() -> SimpleNamespace:
    """Lightweight stand-in for `Settings` exposing only the fields services read.

    Avoids constructing the real (env-required) Settings object.
    """
    return SimpleNamespace(
        blablador_sparql_model="test-model",
        graphdb_base_url="http://graphdb.test",
        graphdb_repository="testrepo",
        sparql_timeout=30.0,
        # Off by default: most tests mock a plain (non-streamed) completion.
        llm_stream_tool_loop=False,
        persist_thinking=True,
        chat_history_depth=5,
        chat_max_tool_iterations=5,
        system_prompt_path="dummy_system.md",
        answer_system_prompt_path="dummy_answer.md",
        # Off by default, so a turn's events are not mixed with title events; the
        # title tests switch it on.
        generate_session_titles=False,
        session_title_prompt_path="dummy_title.md",
        session_title_timeout=5.0,
        full_table_query_path="dummy_table.rq",
        full_table_columns=["name", "count"],
    )


@pytest.fixture
def sparql_results_json() -> str:
    """A sample SPARQL SELECT JSON result with a typed (integer) literal column."""
    return (
        '{"head": {"vars": ["name", "count"]},'
        '"results": {"bindings": ['
        '{"name": {"type": "literal", "value": "Rose"},'
        ' "count": {"type": "literal", "value": "5",'
        ' "datatype": "http://www.w3.org/2001/XMLSchema#integer"}},'
        '{"name": {"type": "literal", "value": "Tulip"},'
        ' "count": {"type": "literal", "value": "3",'
        ' "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}'
        "]}}"
    )
