import json

import pytest

from src.util.llm_utils import load_prompt, load_tools


class TestLoadPrompt:
    def test_reads_file(self, tmp_path):
        f = tmp_path / "prompt.md"
        f.write_text("hello world", encoding="utf-8")
        assert load_prompt(f) == "hello world"

    def test_applies_format_kwargs(self, tmp_path):
        f = tmp_path / "prompt.md"
        f.write_text("hello {name}", encoding="utf-8")
        assert load_prompt(f, name="bob") == "hello bob"

    def test_no_kwargs_leaves_braces_untouched(self, tmp_path):
        f = tmp_path / "prompt.md"
        f.write_text("SELECT { ?s ?p ?o }", encoding="utf-8")
        assert load_prompt(f) == "SELECT { ?s ?p ?o }"


class TestLoadTools:
    def _write_tool(self, tools_dir, filename, payload):
        tools_dir.mkdir(exist_ok=True)
        (tools_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    def test_loads_in_sorted_order(self, tmp_path):
        tools_dir = tmp_path / "tools"
        self._write_tool(tools_dir, "b.json", {"function": {"name": "second"}})
        self._write_tool(tools_dir, "a.json", {"function": {"name": "first"}})
        tools = load_tools(tools_dir)
        assert [t["function"]["name"] for t in tools] == ["first", "second"]

    def test_missing_function_name_raises_value_error(self, tmp_path):
        tools_dir = tmp_path / "tools"
        self._write_tool(tools_dir, "bad.json", {"function": {}})
        with pytest.raises(ValueError):
            load_tools(tools_dir)

    def test_empty_dir_raises_runtime_error(self, tmp_path):
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        with pytest.raises(RuntimeError):
            load_tools(tools_dir)
