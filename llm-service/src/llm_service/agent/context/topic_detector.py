"""Topic shift detection for conversation isolation."""

from __future__ import annotations

import glob
import os
import re
from collections import Counter
from typing import Optional

# Candidate local snapshot paths (checked in order before attempting download)
_LOCAL_MODEL_CANDIDATES: list[str] = [
    # knowledge-base sibling repo
    os.path.join(
        os.path.dirname(__file__),
        "../../../../../../knowledge-base/models/"
        "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2/snapshots",
    ),
]

# Continuations: short messages or messages that start with these words are
# almost certainly follow-ups, never new topics.
_CONTINUATION_STARTERS = re.compile(
    r"^(no[,\s]|yes[,\s]|yeah[,\s]|nope[,\s]|ok[,\s]|okay[,\s]|actually[,\s]|"
    r"i mean[,\s]|wait[,\s]|sorry[,\s]|but[,\s]|and[,\s]|also[,\s]|"
    r"can you[,\s]|could you[,\s]|please[,\s]|"
    r"what about|how about|what if|why not|then|so[,\s])",
    re.IGNORECASE,
)

# Messages of ≤ this many words are treated as follow-up continuations
_SHORT_MESSAGE_WORD_LIMIT = 5


class TopicDetector:
    """Detect whether an incoming message starts a new topic.

    Layered detection:
    1. Heuristic fast-path: short messages and anaphoric starters are never shifts.
    2. Sentence-transformer cosine similarity when available (loaded from local
       snapshot first to avoid network dependency).
    3. Token-overlap fallback — but only when the message is long enough that
       sparse overlap is meaningful.
    """

    def __init__(self, threshold: float = 0.55):
        self.threshold = threshold
        self._embedder = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def _load_embedder(self):
        """Try to load SentenceTransformer from local snapshot, then remote."""
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError:
            self._embedder = False
            return

        # 1. Check local snapshot directories first
        for candidate_dir in _LOCAL_MODEL_CANDIDATES:
            snapshots = sorted(glob.glob(os.path.join(candidate_dir, "*")))
            if snapshots:
                try:
                    self._embedder = SentenceTransformer(snapshots[-1])
                    return
                except Exception:
                    continue

        # 2. Fall back to HuggingFace Hub download (may be slow / offline)
        try:
            # Temporarily unset the hf_transfer flag which causes a hard crash
            # when the optional hf_transfer package is missing.
            prev = os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
            try:
                self._embedder = SentenceTransformer(
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                )
            finally:
                if prev is not None:
                    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = prev
        except Exception:
            self._embedder = False

    def _embedding_similarity(self, left: str, right: str) -> Optional[float]:
        if self._embedder is False:
            return None
        if self._embedder is None:
            self._load_embedder()
        if self._embedder is False:
            return None

        vecs = self._embedder.encode([left, right], normalize_embeddings=True)
        return float((vecs[0] * vecs[1]).sum())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

        msg = current_message.strip()

        # Heuristic 1: very short messages are almost always follow-ups
        if len(self._tokenize(msg)) <= _SHORT_MESSAGE_WORD_LIMIT:
            return False

        # Heuristic 2: messages starting with continuation/anaphora markers
        if _CONTINUATION_STARTERS.match(msg):
            return False

        score = self.similarity(previous_context, msg)
        return score < self.threshold
