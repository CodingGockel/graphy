import json
import re
import unicodedata

from src.services.sparql_service import SparqlService
from src.util.exceptions import SparqlDatabaseException
from src.util.llm_utils import load_prompt

_INDEX_NAME = "entity_lucene"
_INDEX_RQ = "src/resources/lucene/entity_lucene.rq"


def _local_name(token: str) -> str:
    """Local name of a class token (`dwc:Organism`, `<...#Organism>`, full URI), alnum-only."""
    token = token.strip().strip("<>")
    token = re.split(r"[:/#]", token)[-1]
    return re.sub(r"[^0-9A-Za-z]+", "", token)


def _fold_diacritics(text: str) -> str:
    """Strip diacritics (ü→u, é→e, …) via Unicode NFKD decomposition. Lets a user term
    with omitted/normalized accents still reach accented labels."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class LuceneService:
    """Sets up and queries the generic `entity_lucene` GraphDB full-text index that maps
    natural-language names to entity URIs. Backs the `resolve_entity` chat tool."""

    def __init__(self, sparql: SparqlService):
        self.sparql = sparql

    async def _drop_index(self, index_name: str) -> None:
        query = f"""
        PREFIX :<http://www.ontotext.com/connectors/lucene#>
        PREFIX inst:<http://www.ontotext.com/connectors/lucene/instance#>
        INSERT DATA {{
            inst:{index_name} :dropConnector "" .
        }}
        """
        try:
            await self.sparql.execute_update(query)
        except SparqlDatabaseException:
            pass

    async def recreate_entity_index(self) -> None:
        await self._drop_index(_INDEX_NAME)
        query = load_prompt(_INDEX_RQ)
        await self.sparql.execute_update(query)

    async def setup_all_indices(self) -> dict:
        """Recreate every Lucene index. Kept for the lucene_setup script's call site.
        Real failures propagate as SparqlDatabaseException."""
        await self.recreate_entity_index()
        return {"entity": "ok"}

    async def search(
        self, term: str, type: str | None = None, limit: int = 5
    ) -> list[dict]:
        """Return ranked entity candidates for `term` from the Lucene index.

        Each token is matched with both a prefix-wildcard and a fuzzy variant for
        better recall on morphology and typos. An optional `type` narrows results by
        the class' local name (prefix-agnostic), so the caller can pass e.g.
        `dwc:Organism` without us needing a prefix map.

        One candidate per entity: its labels (names in several languages, synonyms) are
        joined into one, so `limit` counts entities and the model sees every name.
        """
        raw_tokens = [w for w in term.split() if w.strip()]
        tokens = [re.sub(r"[^0-9A-Za-z]+", "", _fold_diacritics(w)) for w in raw_tokens]
        tokens = [t for t in tokens if t]
        if not tokens:
            return []

        lucene_query = "label:(" + " AND ".join(f"({t}* OR {t}~1)" for t in tokens) + ")"

        type_filter = ""
        if type:
            local = _local_name(type)
            if local:
                type_filter = (
                    f'          FILTER EXISTS {{ ?entity a ?t . '
                    f'FILTER(STRENDS(STR(?t), "{local}")) }}\n'
                )

        query = f"""
        PREFIX luc: <http://www.ontotext.com/connectors/lucene#>
        PREFIX inst: <http://www.ontotext.com/connectors/lucene/instance#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

        SELECT ?entity ?score (GROUP_CONCAT(DISTINCT ?name; separator=" | ") AS ?label) WHERE {{
          ?search a inst:{_INDEX_NAME} ;
                  luc:query "{lucene_query}" ;
                  luc:entities ?entity .
          ?entity rdfs:label ?name .
          ?entity luc:score ?score .
{type_filter}        }} GROUP BY ?entity ?score ORDER BY DESC(?score) LIMIT {int(limit)}
        """

        response_text = await self.sparql.execute(query)
        data = json.loads(response_text)
        bindings = data.get("results", {}).get("bindings", [])

        results: dict[str, dict] = {}
        for b in bindings:
            uri = b.get("entity", {}).get("value")
            if not uri or uri in results:
                continue
            try:
                score = float(b.get("score", {}).get("value", "0"))
            except (TypeError, ValueError):
                score = 0.0
            results[uri] = {
                "uri": uri,
                "label": b.get("label", {}).get("value"),
                "score": score,
            }
        return list(results.values())
