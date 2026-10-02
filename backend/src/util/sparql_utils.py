import json
import re
from typing import Any

# xsd datatypes that should surface as JSON numbers rather than strings.
_INT_DATATYPES = {"integer", "int", "long", "short", "byte", "nonNegativeInteger",
                  "positiveInteger", "nonPositiveInteger", "negativeInteger",
                  "unsignedInt", "unsignedLong", "unsignedShort", "unsignedByte"}
_FLOAT_DATATYPES = {"decimal", "float", "double"}


def _coerce_cell(binding: dict[str, Any]) -> Any:
    """Convert a single SPARQL binding ({type, value, datatype?}) to a Python value,
    casting numeric xsd datatypes to int/float and leaving everything else as a string."""
    value = binding.get("value")
    if value is None:
        return None
    datatype = binding.get("datatype", "")
    local = datatype.rsplit("#", 1)[-1] if datatype else ""
    try:
        if local in _INT_DATATYPES:
            return int(value)
        if local in _FLOAT_DATATYPES:
            return float(value)
    except (TypeError, ValueError):
        return value
    return value


def parse_sparql_bindings(raw_json: str, columns: list[str]) -> dict[str, Any]:
    """Parse a SPARQL JSON results string into {"columns": [...], "rows": [...]}.

    Rows are restricted to and ordered by `columns`; cells absent from a binding are
    None. Numeric cells are coerced via their xsd datatype (see _coerce_cell).
    """
    data = json.loads(raw_json)
    bindings = data.get("results", {}).get("bindings", [])
    rows: list[dict[str, Any]] = []
    for binding in bindings:
        row: dict[str, Any] = {}
        for column in columns:
            cell = binding.get(column)
            row[column] = _coerce_cell(cell) if cell is not None else None
        rows.append(row)
    return {"columns": columns, "rows": rows}


def strip_think(text: str) -> str:
    """Remove <think>...</think> reasoning blocks that some models emit before their
    actual output. Used for both query extraction and the final natural-language answer."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_sparql_query(llm_output: str) -> str:
    llm_output = strip_think(llm_output)

    match = re.search(r"```(?:sparql)?\s*(.*?)```", llm_output, re.DOTALL)

    if match:
        return match.group(1).strip()

    return llm_output.strip()


# Aggregate markers: a query containing any of these legitimately has no LIMIT.
_AGGREGATE_MARKERS = (
    "GROUP BY", "COUNT(", "SUM(", "AVG(", "MIN(", "MAX(", "SAMPLE(", "GROUP_CONCAT(",
)


def ensure_limit(query: str, default_limit: int = 200) -> str:
    """Safety net: append a LIMIT to a SELECT query that lacks one and is not an aggregate,
    so a forgotten LIMIT can't pull thousands of rows (a 413 / context-blowup risk). ASK /
    CONSTRUCT / DESCRIBE and aggregate queries are left untouched."""
    upper = query.upper()
    if "SELECT" not in upper or "LIMIT" in upper:
        return query
    if any(marker in upper for marker in _AGGREGATE_MARKERS):
        return query
    return f"{query.rstrip()}\nLIMIT {int(default_limit)}"


# Forbidden operations as whole words, in any case. A keyword directly preceded by
# `?`, `$`, `:` or a word character is a variable or prefixed name (?insertion, ex:delete).
_FORBIDDEN_KEYWORDS = re.compile(
    r"(?<![?$:\w])(?:INSERT|DELETE|CONSTRUCT|DROP)\b", re.IGNORECASE
)


def validate_query(llm_output: str) -> bool:
    return _FORBIDDEN_KEYWORDS.search(llm_output) is None
