"""Compose the runtime system prompts from KG-agnostic skeletons + the hand-written
per-KG profiles + an auto-extracted schema snapshot of the live graph.

Run manually whenever the target GraphDB repository changes:

    cd backend && source .swep-venv/bin/activate && python -m src.services.build_prompt

Outputs (paths from Settings):
  - system_prompt_path        := generic_rules.md  with {{KG_PROFILE}} and {{SCHEMA}} filled in
  - answer_system_prompt_path := generic_answer.md with {{KG_ANSWER_PROFILE}} filled in
  - schema_prefixes_path      := the prefix -> namespace map used in the schema block

The schema is derived purely from the data (classes.rq / properties.rq): which types have
instances, and which predicate points at which kind of object (exact datatype incl. xsd:int
vs xsd:integer, or iri/bnode). GraphDB's declared namespaces are NOT used — on this repo they
cover only engine infrastructure, not the domain vocabularies — so prefixes are derived from
the namespaces that actually appear, keeping the builder graph-agnostic.
"""
import asyncio
import json
import re
from pathlib import Path

import httpx

from src.services.sparql_service import SparqlService
from src.util.config import get_settings

# Standard, cross-graph vocabularies → conventional prefix. Anything not listed here is
# auto-derived from its namespace, so this stays free of any single graph's specifics.
WELL_KNOWN: dict[str, str] = {
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf",
    "http://www.w3.org/2000/01/rdf-schema#": "rdfs",
    "http://www.w3.org/2002/07/owl#": "owl",
    "http://www.w3.org/2001/XMLSchema#": "xsd",
    "http://www.w3.org/2006/time#": "time",
    "http://www.w3.org/2003/01/geo/wgs84_pos#": "geo",
    "http://purl.org/dc/terms/": "dcterms",
    "http://purl.obolibrary.org/obo/": "obo",
    "http://rs.tdwg.org/dwc/terms/": "dwc",
    "http://schema.org/": "schema",
    "http://www.w3.org/2004/02/skos/core#": "skos",
    "http://xmlns.com/foaf/0.1/": "foaf",
    "http://www.wikidata.org/entity/": "wd",
    "http://www.wikidata.org/prop/direct/": "wdt",
}

# T-Box definitional predicates: real, but useless for writing answer queries — keep them out
# of the schema table so they don't invite ontology-exploration queries.
SKIP_PROPERTIES: set[str] = {
    "http://www.w3.org/2000/01/rdf-schema#domain",
    "http://www.w3.org/2000/01/rdf-schema#range",
    "http://www.w3.org/2000/01/rdf-schema#subClassOf",
    "http://www.w3.org/2000/01/rdf-schema#subPropertyOf",
    "http://www.w3.org/2002/07/owl#inverseOf",
    "http://proton.semanticweb.org/protonsys#transitiveOver",
}

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "resources" / "schema"
MAX_OBJECT_KINDS = 4  # how many distinct object datatypes to list per predicate

# strip comments 
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _load_clean(path: str) -> str:
    """Read a template/profile and drop its HTML maintainer comments."""
    return _COMMENT_RE.sub("", Path(path).read_text(encoding="utf-8")).strip()


def _split(uri: str) -> tuple[str, str]:
    """Split a URI into (namespace, local name) at the last '#' or '/'."""
    i = max(uri.rfind("#"), uri.rfind("/"))
    return uri[: i + 1], uri[i + 1 :]


class PrefixRegistry:
    """Assigns a prefix to every namespace seen, recording only those actually used."""

    def __init__(self) -> None:
        self._ns_to_prefix: dict[str, str] = {}
        self.used: dict[str, str] = {}  # prefix -> namespace

    def _derive(self, ns: str) -> str:
        seg = re.sub(r"[^A-Za-z0-9]", "", ns.rstrip("#/").rsplit("/", 1)[-1].rsplit("#", 1)[-1])
        seg = seg or "ns"
        existing = set(self._ns_to_prefix.values())
        cand, n = seg, 1
        while cand in existing:
            n += 1
            cand = f"{seg}{n}"
        return cand

    def prefix_for(self, ns: str) -> str:
        prefix = self._ns_to_prefix.get(ns) or WELL_KNOWN.get(ns) or self._derive(ns)
        self._ns_to_prefix[ns] = prefix
        self.used[prefix] = ns
        return prefix

    def curie(self, uri: str) -> str:
        ns, local = _split(uri)
        if not local:
            return f"<{uri}>"
        return f"{self.prefix_for(ns)}:{local}"


def _render_kind(kind: str, reg: PrefixRegistry) -> str:
    if kind in ("iri", "bnode"):
        return kind
    if kind.startswith("rdf:langString@"):
        return "@" + kind.split("@", 1)[1]
    if kind.startswith("http"):
        return reg.curie(kind)
    return kind


def _render_classes(rows: list[dict], reg: PrefixRegistry) -> str:
    lines = ["## Classes (types that have instances)", "", "| Class | Instances |", "|---|---|"]
    for r in rows:
        lines.append(f"| {reg.curie(r['class']['value'])} | {r['n']['value']} |")
    return "\n".join(lines)


def _render_properties(rows: list[dict], reg: PrefixRegistry) -> str:
    grouped: dict[str, list[tuple[str, int]]] = {}
    for r in rows:
        p = r["p"]["value"]
        if p in SKIP_PROPERTIES:
            continue
        grouped.setdefault(p, []).append((r["kind"]["value"], int(r["n"]["value"])))

    lines = [
        "## Properties (predicate → object type, by usage)",
        "",
        "| Property | Object type(s) |",
        "|---|---|",
    ]
    # Most-used predicates first — those are the ones worth querying.
    for p in sorted(grouped, key=lambda k: -sum(c for _, c in grouped[k])):
        kinds = sorted(grouped[p], key=lambda kc: -kc[1])[:MAX_OBJECT_KINDS]
        rendered = ", ".join(_render_kind(k, reg) for k, _ in kinds)
        lines.append(f"| {reg.curie(p)} | {rendered} |")
    return "\n".join(lines)


def _render_prefix_block(reg: PrefixRegistry) -> str:
    lines = ["## Prefixes", "", "```sparql"]
    lines += [f"PREFIX {p}: <{reg.used[p]}>" for p in sorted(reg.used)]
    lines.append("```")
    return "\n".join(lines)


def _render_schema(classes_rows: list[dict], props_rows: list[dict]) -> tuple[PrefixRegistry, str]:
    reg = PrefixRegistry()
    classes_md = _render_classes(classes_rows, reg)
    props_md = _render_properties(props_rows, reg)
    header = "# Schema (auto-extracted from the live graph — complete and verified)"
    body = "\n\n".join([header, _render_prefix_block(reg), classes_md, props_md])
    return reg, body


def _compose(template_path: str, out_path: str, **markers: str) -> None:
    text = _load_clean(template_path)
    for key, value in markers.items():
        text = text.replace("{{" + key + "}}", value)
    Path(out_path).write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


async def _run_query(sparql: SparqlService, rq_name: str) -> list[dict]:
    query = (SCHEMA_DIR / rq_name).read_text(encoding="utf-8")
    raw = await sparql.execute(query)
    return json.loads(raw)["results"]["bindings"]


async def build() -> None:
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        sparql = SparqlService(client=client, settings=settings, timeout=60.0)
        classes_rows = await _run_query(sparql, "classes.rq")
        props_rows = await _run_query(sparql, "properties.rq")

    reg, schema_md = _render_schema(classes_rows, props_rows)

    prefixes_path = Path(settings.schema_prefixes_path)
    prefixes_path.parent.mkdir(parents=True, exist_ok=True)
    prefixes_path.write_text(json.dumps(reg.used, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {prefixes_path} ({len(reg.used)} prefixes, "
          f"{len(classes_rows)} classes, {len(props_rows)} property/datatype rows)")

    _compose(
        settings.generic_rules_path,
        settings.system_prompt_path,
        KG_PROFILE=_load_clean(settings.kg_profile_path),
        SCHEMA=schema_md,
    )
    _compose(
        settings.generic_answer_path,
        settings.answer_system_prompt_path,
        KG_ANSWER_PROFILE=_load_clean(settings.kg_answer_profile_path),
    )


if __name__ == "__main__":
    asyncio.run(build())
