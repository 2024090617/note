"""Tests for tools module."""

from pathlib import Path

from digimate.tools.base import ToolRegistry
from digimate.tools.file_ops import make_file_tools
from digimate.tools.search_ops import make_search_tools
from digimate.tools.git_ops import make_git_tools
from digimate.core.types import ToolResult


def test_tool_registry():
    reg = ToolRegistry(workdir="/tmp")
    reg.register("echo", lambda text="": ToolResult(True, text), mutating=False)
    result = reg.execute("echo", {"text": "hello"})
    assert result.success
    assert result.output == "hello"


def test_unknown_tool():
    reg = ToolRegistry()
    result = reg.execute("nonexistent", {})
    assert not result.success
    assert "Unknown tool" in result.error


def test_file_read_write(tmp_path):
    def resolve(p):
        return (tmp_path / p).resolve() if not Path(p).is_absolute() else Path(p)

    tools = make_file_tools(resolve)
    # create a file
    cr_fn, _ = tools["create_file"]
    result = cr_fn(path="test.txt", content="hello world")
    assert result.success

    # read it back
    rd_fn, _ = tools["read_file"]
    result = rd_fn(path="test.txt")
    assert result.success
    assert "hello world" in result.output

    # patch it
    patch_fn, _ = tools["patch_file"]
    result = patch_fn(path="test.txt", old_string="hello", new_string="goodbye")
    assert result.success

    # verify patch
    result = rd_fn(path="test.txt")
    assert "goodbye world" in result.output


def test_file_read_auto_cap(tmp_path):
    def resolve(p):
        return (tmp_path / p).resolve() if not Path(p).is_absolute() else Path(p)

    tools = make_file_tools(resolve, read_file_auto_limit=50)
    # Create a large file
    cr_fn, _ = tools["create_file"]
    cr_fn(path="big.txt", content="\n".join(f"line {i}" for i in range(200)))

    rd_fn, _ = tools["read_file"]
    result = rd_fn(path="big.txt")
    assert result.success
    assert result.data.get("auto_capped") is True
    assert result.data["lines_read"] <= 200


def test_list_directory(tmp_path):
    def resolve(p):
        return (tmp_path / p).resolve() if not Path(p).is_absolute() else Path(p)

    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    (tmp_path / "sub").mkdir()

    tools = make_file_tools(resolve)
    ls_fn, _ = tools["list_directory"]
    result = ls_fn(path=".")
    assert result.success
    assert "a.txt" in result.output
    assert "sub/" in result.output


def test_search_files(tmp_path):
    def resolve(p):
        return (tmp_path / p).resolve() if not Path(p).is_absolute() else Path(p)

    (tmp_path / "foo.py").write_text("def hello(): pass")
    (tmp_path / "bar.txt").write_text("other")

    tools = make_search_tools(resolve)
    sf_fn, _ = tools["search_files"]
    result = sf_fn(pattern="*.py")
    assert result.success
    assert "foo.py" in result.output


def test_grep(tmp_path):
    def resolve(p):
        return (tmp_path / p).resolve() if not Path(p).is_absolute() else Path(p)

    (tmp_path / "code.py").write_text("import os\nprint('hello')\n")

    tools = make_search_tools(resolve)
    grep_fn, _ = tools["grep"]
    result = grep_fn(pattern="import")
    assert result.success
    assert "import os" in result.output


def test_mutating_registry():
    reg = ToolRegistry()
    reg.register("r", lambda: ToolResult(True, ""), mutating=False)
    reg.register("w", lambda: ToolResult(True, ""), mutating=True)
    assert "w" in reg.mutating_tools()
    assert "r" not in reg.mutating_tools()
