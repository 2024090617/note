"""Tests for workspace scanner and rules."""

import json

from digimate.workspace.scanner import scan_workspace, WorkspaceManifest
from digimate.workspace.rules import discover_instruction_files


def test_scan_workspace(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("const x = 1;")

    m = scan_workspace(str(tmp_path), cache=False)
    assert "python" in m.languages
    assert "typescript" in m.languages
    assert m.file_count >= 3


def test_scan_workspace_cache(tmp_path):
    (tmp_path / "hello.py").write_text("x = 1")
    m1 = scan_workspace(str(tmp_path), cache=True)
    m2 = scan_workspace(str(tmp_path), cache=True)
    assert m1.file_count == m2.file_count


def test_manifest_render():
    m = WorkspaceManifest(
        root="/test", languages=["python", "typescript"],
        frameworks=["node"], structure=["src/", "  app.py"], file_count=5,
    )
    rendered = m.render()
    assert "python" in rendered
    assert "typescript" in rendered


def test_discover_instructions_empty(tmp_path):
    result = discover_instruction_files(str(tmp_path), personal=False)
    assert result == {}


def test_discover_instructions_claude_md(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("# Project rules\nUse pytest.")
    result = discover_instruction_files(str(tmp_path), personal=False)
    assert "CLAUDE.md" in result
    assert "pytest" in result["CLAUDE.md"]


def test_discover_instructions_digimate_rules(tmp_path):
    rules_dir = tmp_path / ".digimate" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "coding.md").write_text("Always use type hints.")
    result = discover_instruction_files(str(tmp_path), personal=False)
    assert any("coding.md" in k for k in result)
