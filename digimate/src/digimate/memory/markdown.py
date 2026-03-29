"""Claude Code–style markdown memory.

Auto-memory (agent-written):
- <memory_dir>/MEMORY.md  (first 200 lines loaded)
- <memory_dir>/topics/<slug>.md  (on-demand via recall)

Instruction file discovery is handled separately by
``digimate.workspace.rules.discover_instruction_files``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from digimate.memory.base import MemoryEntry, MemoryStrategy

MAX_MEMORY_PROMPT_LINES = 200


class MarkdownMemory(MemoryStrategy):
    """Hierarchical markdown memory."""

    def __init__(self, workdir: str = ".", memory_dir: Optional[str] = None) -> None:
        resolved = memory_dir or str(Path(workdir) / ".digimate" / "memory")
        super().__init__(memory_dir=resolved, workdir=workdir)
        self.initialize()

    @property
    def name(self) -> str:
        return "claude-code"

    def initialize(self) -> None:
        mem = Path(self.memory_dir)
        mem.mkdir(parents=True, exist_ok=True)
        (mem / "topics").mkdir(exist_ok=True)

        memory_md = mem / "MEMORY.md"
        if not memory_md.exists():
            memory_md.write_text(
                f"# Agent Memory\n\n_Auto-maintained. "
                f"Created {datetime.now().strftime('%Y-%m-%d')}._\n\n"
            )

    # ── Store ────────────────────────────────────────────────────────

    def store(self, content: str, topic: Optional[str] = None) -> str:
        if topic:
            path = Path(self.memory_dir) / "topics" / f"{_safe_filename(topic)}.md"
            existed = path.exists()
            with open(path, "a", encoding="utf-8") as f:
                if not existed:
                    f.write(f"# {topic}\n\n")
                f.write(f"- {content}\n")
            return f"Stored in topics/{path.name}"
        else:
            path = Path(self.memory_dir) / "MEMORY.md"
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"- {content}\n")
            return "Stored in MEMORY.md"

    # ── Recall ───────────────────────────────────────────────────────

    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        keywords = _tokenize_query(query)
        results: List[MemoryEntry] = []

        results.extend(self._search_file(Path(self.memory_dir) / "MEMORY.md", keywords))

        topics_dir = Path(self.memory_dir) / "topics"
        if topics_dir.is_dir():
            for f in sorted(topics_dir.glob("*.md")):
                results.extend(self._search_file(f, keywords))

        results.sort(key=lambda e: e.score, reverse=True)
        return results[:limit]

    # ── List ─────────────────────────────────────────────────────────

    def list_memories(self) -> List[str]:
        items: List[str] = []
        mem_path = Path(self.memory_dir) / "MEMORY.md"
        if mem_path.exists():
            n = sum(1 for _ in open(mem_path, encoding="utf-8"))
            items.append(f"[auto-memory] MEMORY.md ({n} lines)")

        topics_dir = Path(self.memory_dir) / "topics"
        if topics_dir.is_dir():
            for f in sorted(topics_dir.glob("*.md")):
                n = sum(1 for _ in open(f, encoding="utf-8"))
                items.append(f"[topic] topics/{f.name} ({n} lines)")
        return items

    # ── Prompt context ───────────────────────────────────────────────

    def get_prompt_context(self, max_tokens: int = 0) -> str:
        blocks: List[str] = []
        budget = max_tokens if max_tokens > 0 else float("inf")
        used = 0

        def _est(text: str) -> int:
            cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff'
                      or '\u3400' <= c <= '\u4dbf'
                      or '\uf900' <= c <= '\ufaff')
            non_cjk = len(text) - cjk
            return max(1, non_cjk // 4 + cjk * 2 // 3)

        # MEMORY.md (first N lines)
        mem_path = Path(self.memory_dir) / "MEMORY.md"
        if mem_path.exists() and used < budget:
            try:
                lines = mem_path.read_text(encoding="utf-8").splitlines()
                max_lines = MAX_MEMORY_PROMPT_LINES
                if budget != float("inf"):
                    remaining_chars = int((budget - used) * 4)
                    max_lines = min(max_lines, max(10, remaining_chars // 60))
                truncated = lines[:max_lines]
                if len(lines) > max_lines:
                    truncated.append(
                        f"\n... ({len(lines) - max_lines} more lines — "
                        "use memory_recall to search)"
                    )
                text = "\n".join(truncated).strip()
                if text:
                    blocks.append(f"<!-- MEMORY.md -->\n{text}")
                    used += _est(text)
            except Exception:
                pass

        # Topic file names (loaded on-demand)
        topics_dir = Path(self.memory_dir) / "topics"
        if topics_dir.is_dir():
            topic_names = [f.stem for f in sorted(topics_dir.glob("*.md"))]
            if topic_names:
                blocks.append(
                    f"<!-- Topics (use memory_recall): {', '.join(topic_names)} -->"
                )

        if not blocks:
            return ""
        return "\n\n".join(blocks)

    # ── Search ───────────────────────────────────────────────────────

    @staticmethod
    def _search_file(path: Path, keywords: List[str]) -> List[MemoryEntry]:
        if not path.is_file():
            return []
        results: List[MemoryEntry] = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            lower = stripped.lower()
            hits = sum(1 for kw in keywords if kw in lower)
            if hits > 0:
                results.append(
                    MemoryEntry(content=stripped, source=str(path), score=hits / len(keywords))
                )
        return results


def _safe_filename(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower())
    return safe.strip("-") or "general"


def _tokenize_query(query: str) -> List[str]:
    """Split query into keywords, CJK-aware.

    English words are split by whitespace. CJK characters are emitted
    individually so that substring matching against memory lines works.
    """
    import re as _re
    return _re.findall(
        r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]|[a-zA-Z0-9_]+",
        query.lower(),
    )
