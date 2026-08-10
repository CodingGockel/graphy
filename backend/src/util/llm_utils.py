from pathlib import Path
import json
from typing import Any

def load_prompt(prompt_path: str | Path, **kwargs) -> str:
    content = Path(prompt_path).read_text(encoding="utf-8")
    return content.format(**kwargs) if kwargs else content

# src/resources/llm_tools/ — resolved relative to the package so it works
# regardless of the current working directory.
_TOOLS_DIR = Path(__file__).resolve().parents[1] / "resources" / "llm_tools"

def load_tools(tools_dir: Path = _TOOLS_DIR) -> list[dict[str, Any]]:
    """Load all LLM tool definitions from the JSON files in `tools_dir`.

    Each file holds one tool object (the schema sent to the LLM). Files are
    loaded in sorted filename order so the tool list is deterministic. Intended
    to be called once at import time, not per request.
    """
    tools: list[dict[str, Any]] = []
    for path in sorted(tools_dir.glob("*.json")):
        tool = json.loads(path.read_text(encoding="utf-8"))
        if not tool.get("function", {}).get("name"):
            raise ValueError(f"Tool file {path} is missing 'function.name'")
        tools.append(tool)
    if not tools:
        raise RuntimeError(f"No tool definitions found in {tools_dir}")
    return tools