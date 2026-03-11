"""Claude Code memory strategy.

Mirrors the memory model used by Claude Code (Anthropic):

1. **Instruction files** (human-written, loaded every session):
   - ``CLAUDE.md`` at workdir root
   - ``.claude/CLAUDE.md``
   - ``CLAUDE.local.md`` (personal, not in VCS)
   - ``~/.claude/CLAUDE.md`` (user-level)
   - ``.claude/rules/*.md`` (modular topic rules)

2. **Auto-memory** (agent-written, persisted across sessions):
   - ``<memory_dir>/MEMORY.md`` — concise index (first 200 lines loaded at startup)
   - ``<memory_dir>/topics/<topic>.md`` — detailed topic files (on-demand)

Retrieval is **full-text keyword search** — no vector embeddings.
"""

import fnmatch
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .base import MemoryEntry, MemoryStrategy

logger = logging.getLogger(__name__)

# Instruction file locations relative to workdir (priority order)
_INSTRUCTION_LOCATIONS = [
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    "CLAUDE.local.md",
]

# User-level instruction file
_USER_INSTRUCTION = "~/.claude/CLAUDE.md"

# Maximum lines of MEMORY.md loaded into the prompt
MAX_MEMORY_PROMPT_LINES = 200


class ClaudeCodeMemory(MemoryStrategy):
    """
    Claude Code–style memory: hierarchical Markdown files + auto-memory.

    Instruction files are read-only (the human maintains them).
    Auto-memory in ``<memory_dir>/MEMORY.md`` and ``topics/`` is read-write.
    """

    @property
    def name(self) -> str:
        return "claude-code"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        mem = Path(self.memory_dir)
        mem.mkdir(parents=True, exist_ok=True)
        (mem / "topics").mkdir(exist_ok=True)

        # Ensure MEMORY.md exists
        memory_md = mem / "MEMORY.md"
        if not memory_md.exists():
            memory_md.write_text(
                f"# Agent Memory\n\n_Auto-maintained by the agent. "
                f"Created {datetime.now().strftime('%Y-%m-%d')}._\n\n"
            )

        self._instruction_files = self._discover_instruction_files()
        logger.info(
            "ClaudeCodeMemory initialized — %d instruction files, memory_dir=%s",
            len(self._instruction_files),
            self.memory_dir,
        )

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Recall (keyword search)
    # ------------------------------------------------------------------

    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        keywords = query.lower().split()
        results: List[MemoryEntry] = []

        # Search MEMORY.md
        results.extend(self._search_file(Path(self.memory_dir) / "MEMORY.md", keywords))

        # Search topic files
        topics_dir = Path(self.memory_dir) / "topics"
        if topics_dir.is_dir():
            for f in sorted(topics_dir.glob("*.md")):
                results.extend(self._search_file(f, keywords))

        # Search instruction files
        for fpath in self._instruction_files:
            results.extend(self._search_file(Path(fpath), keywords))

        # Sort by score desc, take top N
        results.sort(key=lambda e: e.score, reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_memories(self) -> List[str]:
        items: List[str] = []

        # Instruction files
        for fpath in self._instruction_files:
            items.append(f"[instruction] {fpath}")

        # MEMORY.md
        mem_path = Path(self.memory_dir) / "MEMORY.md"
        if mem_path.exists():
            line_count = sum(1 for _ in open(mem_path, encoding="utf-8"))
            items.append(f"[auto-memory] MEMORY.md ({line_count} lines)")

        # Topic files
        topics_dir = Path(self.memory_dir) / "topics"
        if topics_dir.is_dir():
            for f in sorted(topics_dir.glob("*.md")):
                line_count = sum(1 for _ in open(f, encoding="utf-8"))
                items.append(f"[topic] topics/{f.name} ({line_count} lines)")

        return items

    # ------------------------------------------------------------------
    # Prompt context
    # ------------------------------------------------------------------

    def get_prompt_context(self, max_tokens: int = 0) -> str:
        blocks: List[str] = []

        def _est_tokens(text: str) -> int:
            return max(1, len(text) // 4)

        budget = max_tokens if max_tokens > 0 else float("inf")  # type: ignore[assignment]
        used = 0

        # Load instruction files (full content, but honour budget)
        for fpath in self._instruction_files:
            try:
                text = Path(fpath).read_text(encoding="utf-8").strip()
                if not text:
                    continue
                block = f"<!-- {fpath} -->\n{text}"
                cost = _est_tokens(block)
                if budget != float("inf") and used + cost > budget:
                    # Truncate to fit remaining budget
                    char_remaining = int((budget - used) * 4)
                    if char_remaining > 100:
                        block = block[:char_remaining] + "\n... (truncated to fit context budget)"
                        blocks.append(block)
                        used = budget  # type: ignore[assignment]
                    break
                blocks.append(block)
                used += cost
            except Exception:
                continue

        # Load MEMORY.md (first N lines, further limited by budget)
        mem_path = Path(self.memory_dir) / "MEMORY.md"
        if mem_path.exists() and used < budget:
            try:
                lines = mem_path.read_text(encoding="utf-8").splitlines()
                max_lines = MAX_MEMORY_PROMPT_LINES
                # Tighten line limit when budget is tight
                if budget != float("inf"):
                    remaining_chars = int((budget - used) * 4)
                    # Rough: 60 chars per line average
                    max_lines = min(max_lines, max(10, remaining_chars // 60))
                truncated = lines[:max_lines]
                if len(lines) > max_lines:
                    truncated.append(
                        f"\n... ({len(lines) - max_lines} more lines — "
                        "use memory_recall to search)"
                    )
                text = "\n".join(truncated).strip()
                if text:
                    block = f"<!-- MEMORY.md -->\n{text}"
                    blocks.append(block)
                    used += _est_tokens(block)
            except Exception:
                pass

        # List topic files (names only — loaded on-demand via memory_recall)
        topics_dir = Path(self.memory_dir) / "topics"
        if topics_dir.is_dir():
            topic_names = [f.stem for f in sorted(topics_dir.glob("*.md"))]
            if topic_names:
                blocks.append(
                    f"<!-- Topic files (use memory_recall to read): "
                    f"{', '.join(topic_names)} -->"
                )

        if not blocks:
            return ""

        return "<memory>\n" + "\n\n".join(blocks) + "\n</memory>"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _discover_instruction_files(self) -> List[str]:
        """Find all instruction files that exist."""
        found: List[str] = []
        workdir = Path(self.workdir)

        for rel in _INSTRUCTION_LOCATIONS:
            p = workdir / rel
            if p.is_file():
                found.append(str(p))

        # User-level
        user_file = Path(os.path.expanduser(_USER_INSTRUCTION))
        if user_file.is_file():
            found.append(str(user_file))

        # .claude/rules/*.md
        rules_dir = workdir / ".claude" / "rules"
        if rules_dir.is_dir():
            for f in sorted(rules_dir.glob("*.md")):
                found.append(str(f))

        return found

    @staticmethod
    def _search_file(path: Path, keywords: List[str]) -> List[MemoryEntry]:
        """Search a file for lines matching any keyword. Returns scored entries."""
        if not path.is_file():
            return []
        results: List[MemoryEntry] = []
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return []

        for line in text.splitlines():
            line_lower = line.lower().strip()
            if not line_lower or line_lower.startswith("#"):
                continue
            # Score = fraction of keywords found in the line
            hits = sum(1 for kw in keywords if kw in line_lower)
            if hits > 0:
                score = hits / len(keywords)
                results.append(
                    MemoryEntry(
                        content=line.strip(),
                        source=str(path),
                        score=score,
                    )
                )
        return results


def _safe_filename(name: str) -> str:
    """Sanitize a topic name for use as a filename."""
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name.lower())
    return safe.strip("-") or "general"
