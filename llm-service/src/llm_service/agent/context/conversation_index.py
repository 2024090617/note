"""Conversation vector index backed by sqlite-vec hybrid search."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ..memory.vector_store import VectorStore


class ConversationIndex:
    """Index and search chat messages with optional thread filtering."""

    def __init__(self, workdir: str):
        db_path = Path(workdir) / ".digimate" / "cache" / "conversation_index.db"
        self._store = VectorStore(str(db_path))
        self._enabled = False
        try:
            self._store.open()
            self._enabled = True
        except Exception:
            self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def index_message(self, message_id: str, thread_id: str, role: str, content: str) -> None:
        if not self._enabled:
            return
        doc_id = f"thread:{thread_id}|message:{message_id}|role:{role}"
        try:
            self._store.index_document(doc_id, content)
        except Exception:
            pass

    def search(self, query: str, limit: int = 5, thread_id: Optional[str] = None) -> List[Dict[str, object]]:
        if not self._enabled or not query.strip():
            return []
        try:
            raw = self._store.search(query=query, limit=max(limit * 4, limit), mode="hybrid")
        except Exception:
            return []

        scoped: List[Dict[str, object]] = []
        for doc_id, content, score in raw:
            if thread_id and not doc_id.startswith(f"thread:{thread_id}|"):
                continue
            scoped.append({"doc_id": doc_id, "content": content, "score": float(score)})
            if len(scoped) >= limit:
                break
        return scoped

    def close(self) -> None:
        if not self._enabled:
            return
        self._store.close()
