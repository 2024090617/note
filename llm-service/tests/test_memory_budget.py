"""Tests for token-aware memory get_prompt_context."""

import tempfile
import os

from llm_service.agent.memory.claude_code import ClaudeCodeMemory


def test_get_prompt_context_unlimited():
    """With max_tokens=0 (default), behaviour is unchanged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ClaudeCodeMemory(memory_dir=tmpdir, workdir=tmpdir)
        mem.initialize()
        mem.store("fact one")
        mem.store("fact two")

        ctx = mem.get_prompt_context(max_tokens=0)
        assert "<memory>" in ctx
        assert "fact one" in ctx
        assert "fact two" in ctx


def test_get_prompt_context_tight_budget():
    """With a small max_tokens budget, output is truncated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ClaudeCodeMemory(memory_dir=tmpdir, workdir=tmpdir)
        mem.initialize()

        # Stuff MEMORY.md with many lines
        for i in range(100):
            mem.store(f"fact number {i}: " + "x" * 80)

        # Unlimited
        full_ctx = mem.get_prompt_context(max_tokens=0)
        full_len = len(full_ctx)

        # Tight budget (50 tokens ≈ 200 chars)
        tight_ctx = mem.get_prompt_context(max_tokens=50)

        assert len(tight_ctx) < full_len
        # Should still be valid
        assert "<memory>" in tight_ctx


def test_get_prompt_context_respects_instruction_budget():
    """Instruction files are truncated when budget is tight."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a large CLAUDE.md instruction file
        claude_md = os.path.join(tmpdir, "CLAUDE.md")
        with open(claude_md, "w") as f:
            f.write("# Instructions\n\n" + "- rule line\n" * 200)

        mem = ClaudeCodeMemory(memory_dir=os.path.join(tmpdir, ".mem"), workdir=tmpdir)
        mem.initialize()

        full_ctx = mem.get_prompt_context(max_tokens=0)
        tight_ctx = mem.get_prompt_context(max_tokens=30)

        assert len(tight_ctx) < len(full_ctx)
