"""Phase 3 retrieval reranking with task alignment and recency signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
import re


@dataclass
class RankedItem:
    """Ranked retrieval item with scoring breakdown."""

    payload: Dict[str, Any]
    final_score: float
    relevance_score: float
    recency_score: float
    task_alignment_score: float


class RetrievalReranker:
    """Combine relevance, recency, and task-alignment into a final ranking."""

    def __init__(
        self,
        relevance_weight: float = 0.6,
        recency_weight: float = 0.25,
        task_alignment_weight: float = 0.15,
    ):
        self.relevance_weight = relevance_weight
        self.recency_weight = recency_weight
        self.task_alignment_weight = task_alignment_weight

    def rerank_snippets(
        self,
        snippets: List[Dict[str, Any]],
        query: str,
        task_context: str,
        message_recency_index: Optional[Dict[str, float]] = None,
        limit: int = 4,
    ) -> List[Dict[str, Any]]:
        """Rerank conversation snippets and return top N."""
        ranked: List[RankedItem] = []
        for item in snippets:
            content = str(item.get("content", ""))
            doc_id = str(item.get("doc_id", ""))
            relevance = self._normalize_relevance(item.get("score", 0.0))
            recency = self._snippet_recency(doc_id, message_recency_index or {})
            alignment = self._task_alignment(content, query, task_context)
            final_score = self._final_score(relevance, recency, alignment)
            ranked.append(
                RankedItem(
                    payload={
                        **item,
                        "rerank": {
                            "final": round(final_score, 4),
                            "relevance": round(relevance, 4),
                            "recency": round(recency, 4),
                            "task_alignment": round(alignment, 4),
                        },
                    },
                    final_score=final_score,
                    relevance_score=relevance,
                    recency_score=recency,
                    task_alignment_score=alignment,
                )
            )

        ranked.sort(key=lambda x: x.final_score, reverse=True)
        return [r.payload for r in ranked[: max(1, limit)]]

    def rerank_memories(
        self,
        memories: List[Any],
        query: str,
        task_context: str,
        limit: int = 3,
    ) -> List[Any]:
        """Rerank memory entries and return top N in original object form."""
        scored: List[tuple[float, Any]] = []
        for mem in memories:
            content = str(getattr(mem, "content", ""))
            relevance = self._normalize_relevance(getattr(mem, "score", 0.0))
            recency = self._memory_recency(getattr(mem, "timestamp", ""))
            alignment = self._task_alignment(content, query, task_context)
            final_score = self._final_score(relevance, recency, alignment)
            scored.append((final_score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[: max(1, limit)]]

    def _final_score(self, relevance: float, recency: float, task_alignment: float) -> float:
        return (
            self.relevance_weight * relevance
            + self.recency_weight * recency
            + self.task_alignment_weight * task_alignment
        )

    def _normalize_relevance(self, raw_score: Any) -> float:
        """Normalize heterogeneous backend scores into [0, 1]."""
        try:
            value = float(raw_score)
        except Exception:
            return 0.0

        if value <= 0.0:
            return 0.0
        if value <= 1.0:
            return value
        # Hybrid search backends can emit values > 1.
        return min(1.0, value / 10.0)

    def _snippet_recency(self, doc_id: str, recency_index: Dict[str, float]) -> float:
        """Get recency score from indexed message id, falling back to neutral."""
        msg_id = self._extract_message_id(doc_id)
        if not msg_id:
            return 0.5
        return recency_index.get(msg_id, 0.5)

    def _memory_recency(self, timestamp: str) -> float:
        """Map memory timestamp to [0, 1] recency score."""
        if not timestamp:
            return 0.5
        try:
            created = datetime.fromisoformat(timestamp)
            age_days = max(0.0, (datetime.now(created.tzinfo) - created).total_seconds() / 86400.0)
            # Exponential-ish decay: recent entries near 1, old entries approach 0.
            return 1.0 / (1.0 + age_days / 7.0)
        except Exception:
            return 0.5

    def _task_alignment(self, content: str, query: str, task_context: str) -> float:
        """Compute lexical overlap against query + active task context."""
        candidate_terms = set(self._tokenize(content))
        if not candidate_terms:
            return 0.0

        intent_terms = set(self._tokenize(f"{query} {task_context}"))
        if not intent_terms:
            return 0.0

        overlap = candidate_terms.intersection(intent_terms)
        union_size = len(candidate_terms.union(intent_terms))
        if union_size == 0:
            return 0.0
        return len(overlap) / union_size

    def _extract_message_id(self, doc_id: str) -> str:
        m = re.search(r"\|message:([^|]+)", doc_id)
        return m.group(1) if m else ""

    def _tokenize(self, text: str) -> List[str]:
        return [tok for tok in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(tok) >= 3]
