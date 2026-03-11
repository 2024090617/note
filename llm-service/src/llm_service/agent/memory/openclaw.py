"""OpenClaw memory strategy.

Mirrors the memory model used by OpenClaw (openclaw.ai):

1. **Daily logs** — append-only daily Markdown files at ``<memory_dir>/daily/YYYY-MM-DD.md``.
   Today's and yesterday's logs are loaded into the prompt at session start.

2. **Long-term memory** — curated ``<memory_dir>/MEMORY.md``, loaded into the prompt
   at session start (first 200 lines).

3. **Hybrid search** — BM25 keyword + vector semantic search via ``VectorStore``
   (SQLite + sqlite-vec + sentence-transformers). Gracefully degrades to
   keyword-only if the optional packages aren't installed.

4. **Pre-compaction flush** — ``flush()`` persists in-flight context before
   the conversation window is compacted.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .base import MemoryEntry, MemoryStrategy

logger = logging.getLogger(__name__)

MAX_MEMORY_PROMPT_LINES = 200


class OpenClawMemory(MemoryStrategy):
    """
    OpenClaw-style memory: daily logs + curated MEMORY.md + hybrid vector search.
    """

    def __init__(self, memory_dir: str, workdir: str = "."):
        super().__init__(memory_dir, workdir)
        self._vector_store = None  # lazy

    @property
    def name(self) -> str:
        return "openclaw"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        mem = Path(self.memory_dir)
        mem.mkdir(parents=True, exist_ok=True)
        (mem / "daily").mkdir(exist_ok=True)

        # Ensure MEMORY.md exists
        memory_md = mem / "MEMORY.md"
        if not memory_md.exists():
            memory_md.write_text(
                f"# Long-Term Memory\n\n_Curated by the agent. "
                f"Created {datetime.now().strftime('%Y-%m-%d')}._\n\n"
            )

        # Build / update the search index
        self._ensure_vector_store()
        self._index_all_files()

        logger.info("OpenClawMemory initialized — memory_dir=%s", self.memory_dir)

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(self, content: str, topic: Optional[str] = None) -> str:
        if topic and topic.lower() == "long-term":
            path = Path(self.memory_dir) / "MEMORY.md"
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"- {content}\n")
            self._reindex_file(str(path))
            return "Stored in MEMORY.md (long-term)"
        else:
            # Default: daily log
            today = datetime.now().strftime("%Y-%m-%d")
            path = Path(self.memory_dir) / "daily" / f"{today}.md"
            existed = path.exists()
            with open(path, "a", encoding="utf-8") as f:
                if not existed:
                    f.write(f"# {today}\n\n")
                ts = datetime.now().strftime("%H:%M")
                f.write(f"- [{ts}] {content}\n")
            self._reindex_file(str(path))
            return f"Stored in daily/{today}.md"

    # ------------------------------------------------------------------
    # Recall (hybrid search)
    # ------------------------------------------------------------------

    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        store = self._ensure_vector_store()
        if store is None:
            # Fallback to simple keyword search across all files
            return self._keyword_fallback(query, limit)

        results = store.search(query, limit=limit, mode="hybrid")
        return [
            MemoryEntry(
                content=content,
                source=doc_id,
                score=score,
            )
            for doc_id, content, score in results
        ]

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_memories(self) -> List[str]:
        items: List[str] = []
        mem = Path(self.memory_dir)

        # MEMORY.md
        memory_md = mem / "MEMORY.md"
        if memory_md.exists():
            line_count = sum(1 for _ in open(memory_md, encoding="utf-8"))
            items.append(f"[long-term] MEMORY.md ({line_count} lines)")

        # Daily logs
        daily_dir = mem / "daily"
        if daily_dir.is_dir():
            for f in sorted(daily_dir.glob("*.md"), reverse=True):
                line_count = sum(1 for _ in open(f, encoding="utf-8"))
                items.append(f"[daily] daily/{f.name} ({line_count} lines)")

        # Index stats
        store = self._ensure_vector_store()
        if store and store._conn:
            row = store._conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
            items.append(f"[index] {row[0]} chunks in vector store")

        return items

    # ------------------------------------------------------------------
    # Prompt context
    # ------------------------------------------------------------------

    def get_prompt_context(self, max_tokens: int = 0) -> str:
        blocks: List[str] = []
        mem = Path(self.memory_dir)

        def _est_tokens(text: str) -> int:
            return max(1, len(text) // 4)

        budget = max_tokens if max_tokens > 0 else float("inf")  # type: ignore[assignment]
        used = 0

        # MEMORY.md (first N lines, limited by budget)
        memory_md = mem / "MEMORY.md"
        if memory_md.exists():
            try:
                lines = memory_md.read_text(encoding="utf-8").splitlines()
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
                    block = f"<!-- MEMORY.md -->\n{text}"
                    blocks.append(block)
                    used += _est_tokens(block)
            except Exception:
                pass

        # Today's and yesterday's daily logs
        today = datetime.now()
        for delta in (0, 1):
            if used >= budget:
                break
            day = today - timedelta(days=delta)
            day_file = mem / "daily" / f"{day.strftime('%Y-%m-%d')}.md"
            if day_file.is_file():
                try:
                    text = day_file.read_text(encoding="utf-8").strip()
                    if not text:
                        continue
                    label = "today" if delta == 0 else "yesterday"
                    block = f"<!-- daily/{day_file.name} ({label}) -->\n{text}"
                    cost = _est_tokens(block)
                    if budget != float("inf") and used + cost > budget:
                        char_remaining = int((budget - used) * 4)
                        if char_remaining > 80:
                            block = block[:char_remaining] + "\n... (truncated)"
                            blocks.append(block)
                        break
                    blocks.append(block)
                    used += cost
                except Exception:
                    continue

        if not blocks:
            return ""

        return "<memory>\n" + "\n\n".join(blocks) + "\n</memory>"

    # ------------------------------------------------------------------
    # Flush (pre-compaction)
    # ------------------------------------------------------------------

    def flush(self) -> None:
        """Persist any index state."""
        if self._vector_store and self._vector_store._conn:
            self._vector_store._conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_vector_store(self):
        """Lazy-initialize VectorStore."""
        if self._vector_store is not None:
            return self._vector_store

        try:
            from .vector_store import VectorStore

            db_path = str(Path(self.memory_dir) / "index.db")
            self._vector_store = VectorStore(db_path)
            self._vector_store.open()
            return self._vector_store
        except Exception as e:
            logger.warning("VectorStore unavailable: %s", e)
            return None

    def _index_all_files(self) -> None:
        """Index all memory files into the vector store."""
        store = self._ensure_vector_store()
        if store is None:
            return

        mem = Path(self.memory_dir)

        # Index MEMORY.md
        memory_md = mem / "MEMORY.md"
        if memory_md.is_file():
            store.index_document("MEMORY.md", memory_md.read_text(encoding="utf-8"))

        # Index daily logs
        daily_dir = mem / "daily"
        if daily_dir.is_dir():
            for f in daily_dir.glob("*.md"):
                store.index_document(
                    f"daily/{f.name}", f.read_text(encoding="utf-8")
                )

    def _reindex_file(self, file_path: str) -> None:
        """Re-index a single file after it's been modified."""
        store = self._ensure_vector_store()
        if store is None:
            return

        path = Path(file_path)
        if not path.is_file():
            return

        mem = Path(self.memory_dir)
        try:
            rel = path.relative_to(mem)
            doc_id = str(rel)
        except ValueError:
            doc_id = path.name

        store.index_document(doc_id, path.read_text(encoding="utf-8"))

    def _keyword_fallback(self, query: str, limit: int) -> List[MemoryEntry]:
        """Simple keyword search when VectorStore is unavailable."""
        keywords = query.lower().split()
        results: List[MemoryEntry] = []
        mem = Path(self.memory_dir)

        files = [mem / "MEMORY.md"]
        daily_dir = mem / "daily"
        if daily_dir.is_dir():
            files.extend(sorted(daily_dir.glob("*.md"), reverse=True))

        for fpath in files:
            if not fpath.is_file():
                continue
            try:
                text = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            for line in text.splitlines():
                line_lower = line.lower().strip()
                if not line_lower or line_lower.startswith("#"):
                    continue
                hits = sum(1 for kw in keywords if kw in line_lower)
                if hits > 0:
                    results.append(
                        MemoryEntry(
                            content=line.strip(),
                            source=str(fpath),
                            score=hits / len(keywords),
                        )
                    )

        results.sort(key=lambda e: e.score, reverse=True)
        return results[:limit]
