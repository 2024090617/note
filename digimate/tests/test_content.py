"""Tests for core/content.py — truncation guard."""

from digimate.core.content import estimate_tokens, truncate_observation


def test_estimate_tokens():
    assert estimate_tokens("hello") == 1  # 5 chars // 4
    assert estimate_tokens("a" * 400) == 100


def test_truncate_below_limit():
    text = "short text"
    result, overflow = truncate_observation(text, max_tokens=100)
    assert result == text
    assert overflow is None


def test_truncate_above_limit(tmp_path):
    text = "x" * 80_000  # 20K tokens
    result, overflow = truncate_observation(
        text, max_tokens=100, action="test_tool",
        overflow_dir=str(tmp_path / "overflow"),
    )
    assert len(result) < len(text)
    assert overflow is not None
    assert "[Truncated at" in result
    assert (tmp_path / "overflow").exists()
