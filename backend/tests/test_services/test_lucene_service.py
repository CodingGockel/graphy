import json
from unittest.mock import AsyncMock, MagicMock

from src.services.lucene_service import LuceneService, _fold_diacritics, _local_name


def _make_service(*, execute_return="", execute=None):
    sparql = MagicMock()
    sparql.execute = execute if execute is not None else AsyncMock(return_value=execute_return)
    return LuceneService(sparql=sparql), sparql


def _bindings(*rows) -> str:
    """rows: tuples of (uri, label, score)."""
    bindings = [
        {
            "entity": {"value": uri},
            "label": {"value": label},
            "score": {"value": str(score)},
        }
        for uri, label, score in rows
    ]
    return json.dumps({"results": {"bindings": bindings}})


class TestFoldDiacritics:
    def test_strips_umlaut(self):
        assert _fold_diacritics("Tübingen") == "Tubingen"

    def test_strips_accent(self):
        assert _fold_diacritics("café") == "cafe"


class TestLocalName:
    def test_prefixed_name(self):
        assert _local_name("dwc:Organism") == "Organism"

    def test_full_uri(self):
        assert _local_name("<http://example.org/onto#Organism>") == "Organism"


class TestSearch:
    async def test_empty_term_returns_empty(self):
        service, sparql = _make_service()
        assert await service.search("   ") == []
        sparql.execute.assert_not_called()

    async def test_parses_candidates(self):
        service, _ = _make_service(execute_return=_bindings(("http://x/1", "Rose", 2.5)))
        results = await service.search("rose")
        assert results == [{"uri": "http://x/1", "label": "Rose", "score": 2.5}]

    async def test_dedupes_by_uri_keeping_first(self):
        service, _ = _make_service(
            execute_return=_bindings(("http://x/1", "Rose", 2.5), ("http://x/1", "Rosa", 1.0))
        )
        results = await service.search("rose")
        assert len(results) == 1
        assert results[0]["score"] == 2.5

    async def test_no_bindings_returns_empty(self):
        service, _ = _make_service(execute_return='{"results": {"bindings": []}}')
        assert await service.search("rose") == []

    async def test_folds_diacritics_in_query(self):
        service, sparql = _make_service(execute_return='{"results": {"bindings": []}}')
        await service.search("Tübingen")
        sent_query = sparql.execute.await_args.args[0]
        assert "Tubingen" in sent_query

    async def test_type_filter_included_in_query(self):
        service, sparql = _make_service(execute_return='{"results": {"bindings": []}}')
        await service.search("rose", type="dwc:Organism")
        sent_query = sparql.execute.await_args.args[0]
        assert "Organism" in sent_query
        assert "FILTER EXISTS" in sent_query
