"""Large-content guard — truncate oversized tool results.

Provides a universal safety-net (Layer 1) that prevents any single
tool observation from consuming too much of the context window.

Full content is saved to an overflow file on disk for later retrieval
via ``read_file`` with specific line ranges.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple


def estimate_tokens(text: str) -> int:
    """Fast token estimate, CJK-aware.

    English/code averages ~4 chars per token.
    CJK characters average ~1.5 chars per token (each char ≈ 0.7 tokens).
    """
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff'
              or '\u3400' <= c <= '\u4dbf'
              or '\uf900' <= c <= '\ufaff')
    non_cjk = len(text) - cjk
    return max(1, non_cjk // 4 + cjk * 2 // 3)


def truncate_observation(
    text: str,
    max_tokens: int,
    action: str = "",
    overflow_dir: str = ".digimate/cache/overflow",
) -> Tuple[str, Optional[str]]:
    """Truncate *text* if it exceeds *max_tokens*.

    Returns:
        (possibly_truncated_text, overflow_path_or_None)

    If the text fits within the budget, it is returned unchanged with
    ``overflow_path=None``.

    If it exceeds the budget the full content is written to *overflow_dir*
    and the returned text is the first *max_tokens* worth of characters
    with a footer directing the LLM to use ``read_file`` on the overflow.
    """
    tokens = estimate_tokens(text)
    if tokens <= max_tokens:
        return text, None

    # Save full content to overflow file
    overflow = Path(overflow_dir)
    overflow.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_action = action.replace("/", "_").replace(" ", "_")[:40]
    filename = f"{safe_action}_{ts}.txt"
    overflow_path = overflow / filename
    overflow_path.write_text(text, encoding="utf-8")

    # Truncate: keep first max_tokens * 4 chars (inverse of estimate)
    keep_chars = max_tokens * 4
    truncated = text[:keep_chars]

    footer = (
        f"\n\n[Truncated at ~{max_tokens:,} tokens. "
        f"Full content ({tokens:,} tokens) saved to: {overflow_path}. "
        f"Use read_file with start_line/end_line to access specific sections.]"
    )
    return truncated + footer, str(overflow_path)
