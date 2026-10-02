from src.util.sparql_utils import (
    count_rows,
    ensure_limit,
    extract_sparql_query,
    parse_sparql_bindings,
    results_to_json,
    results_to_text,
    strip_think,
    validate_query,
)


class TestParseSparqlBindings:
    def test_restricts_and_orders_columns(self, sparql_results_json):
        result = parse_sparql_bindings(sparql_results_json, ["count", "name"])
        assert result["columns"] == ["count", "name"]
        assert list(result["rows"][0].keys()) == ["count", "name"]

    def test_coerces_integer_datatype(self, sparql_results_json):
        result = parse_sparql_bindings(sparql_results_json, ["name", "count"])
        assert result["rows"][0] == {"name": "Rose", "count": 5}
        assert isinstance(result["rows"][0]["count"], int)

    def test_coerces_float_datatype(self):
        raw = (
            '{"results": {"bindings": [{"v": {"value": "1.5",'
            ' "datatype": "http://www.w3.org/2001/XMLSchema#decimal"}}]}}'
        )
        result = parse_sparql_bindings(raw, ["v"])
        assert result["rows"][0]["v"] == 1.5

    def test_missing_cell_is_none(self, sparql_results_json):
        result = parse_sparql_bindings(sparql_results_json, ["name", "absent"])
        assert result["rows"][0]["absent"] is None

    def test_unparseable_numeric_falls_back_to_string(self):
        raw = (
            '{"results": {"bindings": [{"v": {"value": "not-a-number",'
            ' "datatype": "http://www.w3.org/2001/XMLSchema#integer"}}]}}'
        )
        result = parse_sparql_bindings(raw, ["v"])
        assert result["rows"][0]["v"] == "not-a-number"

    def test_no_bindings(self):
        result = parse_sparql_bindings('{"results": {"bindings": []}}', ["x"])
        assert result == {"columns": ["x"], "rows": []}


class TestStoredResults:
    def test_json_round_trip(self, sparql_results_json):
        stored = results_to_json(sparql_results_json)
        assert isinstance(stored, dict)
        assert results_to_json(results_to_text(stored)) == stored

    def test_non_json_text_is_kept_as_string(self):
        assert results_to_json("not json") == "not json"
        assert results_to_text("not json") == "not json"

    def test_count_rows(self, sparql_results_json):
        assert count_rows(results_to_json(sparql_results_json)) == 2

    def test_count_rows_is_none_without_bindings(self):
        assert count_rows({"head": {}, "boolean": True}) is None
        assert count_rows("not json") is None


class TestEnsureLimit:
    def test_appends_limit_to_plain_select(self):
        out = ensure_limit("SELECT ?s WHERE { ?s ?p ?o }", default_limit=50)
        assert out.endswith("LIMIT 50")

    def test_leaves_existing_limit(self):
        query = "SELECT ?s WHERE { ?s ?p ?o } LIMIT 10"
        assert ensure_limit(query) == query

    def test_leaves_aggregate_query(self):
        query = "SELECT (COUNT(?s) AS ?n) WHERE { ?s ?p ?o }"
        assert ensure_limit(query) == query

    def test_leaves_group_by_query(self):
        query = "SELECT ?t WHERE { ?s a ?t } GROUP BY ?t"
        assert ensure_limit(query) == query

    def test_leaves_ask_query(self):
        query = "ASK { ?s ?p ?o }"
        assert ensure_limit(query) == query


class TestValidateQuery:
    def test_allows_select(self):
        assert validate_query("SELECT ?s WHERE { ?s ?p ?o }") is True

    def test_allows_ask(self):
        assert validate_query("ASK { ?s ?p ?o }") is True

    def test_rejects_insert(self):
        assert validate_query("INSERT DATA { <a> <b> <c> }") is False

    def test_rejects_delete(self):
        assert validate_query("DELETE WHERE { ?s ?p ?o }") is False

    def test_rejects_construct(self):
        assert validate_query("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }") is False

    def test_rejects_drop(self):
        assert validate_query("DROP GRAPH <g>") is False

    def test_rejects_lowercase_keyword(self):
        assert validate_query("insert data { <a> <b> <c> }") is False

    def test_allows_variable_named_like_keyword(self):
        assert validate_query("SELECT ?insertion WHERE { ?s ?p ?insertion }") is True

    def test_allows_keyword_as_variable(self):
        assert validate_query("SELECT ?delete WHERE { ?s ?p ?delete }") is True

    def test_allows_keyword_as_prefixed_name(self):
        assert validate_query("SELECT ?s WHERE { ?s ex:drop ?o }") is True

    def test_allows_keyword_inside_longer_word(self):
        query = 'SELECT ?s WHERE { ?s rdfs:label "Constructa" }'
        assert validate_query(query) is True

    def test_allows_keyword_in_string_literal(self):
        query = 'SELECT ?s WHERE { ?s rdfs:label ?l FILTER(CONTAINS(LCASE(?l), "drop")) }'
        assert validate_query(query) is True
        assert validate_query("SELECT ?s WHERE { ?s rdfs:label 'insert here' }") is True
        assert validate_query('SELECT ?s WHERE { ?s ?p """delete\nme""" }') is True

    def test_allows_keyword_in_iri(self):
        assert validate_query("SELECT ?o WHERE { <http://example.org/delete> ?p ?o }") is True

    def test_allows_keyword_in_comment(self):
        assert validate_query("SELECT ?s WHERE { ?s ?p ?o } # do not drop this") is True

    def test_rejects_keyword_next_to_a_literal(self):
        assert validate_query('INSERT DATA { <a> <b> "drop" }') is False
        assert validate_query('SELECT ?s WHERE { ?s ?p "x" } ; DROP GRAPH <g>') is False

    def test_comparison_operators_do_not_hide_a_keyword(self):
        query = "SELECT ?s WHERE { ?s ?p ?o FILTER(?o < 5) } ; DELETE WHERE { ?a ?b ?c FILTER(?c > 1) }"
        assert validate_query(query) is False


class TestExtractSparqlQuery:
    def test_extracts_from_sparql_fence(self):
        out = extract_sparql_query("```sparql\nSELECT ?s WHERE { ?s ?p ?o }\n```")
        assert out == "SELECT ?s WHERE { ?s ?p ?o }"

    def test_extracts_from_bare_fence(self):
        out = extract_sparql_query("```\nASK { ?s ?p ?o }\n```")
        assert out == "ASK { ?s ?p ?o }"

    def test_returns_bare_text_when_no_fence(self):
        out = extract_sparql_query("  SELECT ?s WHERE { ?s ?p ?o }  ")
        assert out == "SELECT ?s WHERE { ?s ?p ?o }"

    def test_strips_think_block(self):
        out = extract_sparql_query("<think>reasoning</think>```sparql\nASK {}\n```")
        assert out == "ASK {}"


class TestStripThink:
    def test_removes_think_block(self):
        assert strip_think("<think>hidden</think>visible") == "visible"

    def test_removes_multiline_think_block(self):
        assert strip_think("a<think>\nx\ny\n</think>b") == "ab"

    def test_leaves_text_without_think(self):
        assert strip_think("just text") == "just text"
