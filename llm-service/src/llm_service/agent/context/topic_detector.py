"""Topic shift detection for conversation isolation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional


class TopicDetector:
    """Detect whether an incoming message starts a new topic.

    Uses sentence-transformer cosine similarity when available, with a
    token-overlap fallback to keep behavior deterministic without optional deps.
    """

    def __init__(self, threshold: float = 0.55):
        self.threshold = threshold
        self._embedder = None

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _token_similarity(self, left: str, right: str) -> float:
        lt = Counter(self._tokenize(left))
        rt = Counter(self._tokenize(right))
        if not lt or not rt:
            return 1.0 if left.strip() == right.strip() else 0.0

        common = set(lt) & set(rt)
        dot = sum(lt[t] * rt[t] for t in common)
        l2_left = sum(v * v for v in lt.values()) ** 0.5
        l2_right = sum(v * v for v in rt.values()) ** 0.5
        if l2_left == 0 or l2_right == 0:
            return 0.0
        return dot / (l2_left * l2_right)

    def _embedding_similarity(self, left: str, right: str) -> Optional[float]:
        if self._embedder is False:
            return None
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._embedder = SentenceTransformer(
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                )
            except Exception:
                self._embedder = False
                return None

        assert self._embedder is not None
        vecs = self._embedder.encode([left, right], normalize_embeddings=True)
        left_vec, right_vec = vecs[0], vecs[1]
        return float((left_vec * right_vec).sum())

    def similarity(self, left: str, right: str) -> float:
        if not left.strip() or not right.strip():
            return 1.0

        emb = self._embedding_similarity(left, right)
        if emb is not None:
            return emb
        return self._token_similarity(left, right)

    def is_topic_shift(self, previous_context: str, current_message: str) -> bool:
        """Return True when the message is likely unrelated to previous context."""
        if not previous_context.strip():
            return False
        score = self.similarity(previous_context, current_message)
        return score < self.threshold
