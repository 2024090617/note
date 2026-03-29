"""Tests for prompt/system.py."""

from digimate.prompt.system import build_system_prompt, render_tools_block


class FakeToolDef:
    def __init__(self, name, desc="", mutating=False, schema=None):
        self.name = name
        self.description = desc
        self.mutating = mutating
        self.schema = schema or {}


def test_build_system_prompt_minimal():
    prompt = build_system_prompt()
    assert "digimate" in prompt
    assert "Response Format" in prompt


def test_build_system_prompt_with_sections():
    prompt = build_system_prompt(
        workspace_block="Root: /test\nLanguages: python",
        instructions={"CLAUDE.md": "Use pytest"},
        memory_block="Remember: use --tb=short",
        working_memory_block="<working_memory>...</working_memory>",
    )
    assert "<workspace>" in prompt
    assert "Use pytest" in prompt
    assert "Remember:" in prompt
    assert "<working_memory>" in prompt


def test_render_tools_block():
    tools = [
        FakeToolDef("read_file", "Read a file", mutating=False),
        FakeToolDef("write_file", "Write a file", mutating=True),
    ]
    block = render_tools_block(tools)
    assert "read_file" in block
    assert "[mutating]" in block
    assert "write_file" in block


def test_render_tools_block_empty():
    assert render_tools_block([]) == ""
