"""SQLite-backed BM25 + optional vector hybrid search store.

Optional dependencies (gracefully degrades):
- ``sqlite-vec``  — hardware-accelerated vector queries in SQLite
- ``sentence-transformers`` — local embedding model

Without these the store falls back to BM25-only keyword search,
which requires no extra dependencies beyond the stdlib.
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Chunking params ──────────────────────────────────────────────
CHUNK_TARGET_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 80

# ── Embedding model ──────────────────────────────────────────────
_EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_EMBED_DIM = 384


# ── Helpers ──────────────────────────────────────────────────────


def _rough_tokenize(text: str) -> List[str]:
    """Tokenize text for BM25, with CJK support.

    English/code: split on word boundaries (``\\w+``).
    CJK characters: emit unigrams + bigrams so that both single-char
    and two-char terms are searchable without a segmentation library.
    """
    tokens: List[str] = []
    cjk_buf: List[str] = []

    def _flush_cjk() -> None:
        if not cjk_buf:
            return
        # unigrams
        tokens.extend(cjk_buf)
        # bigrams for compound-word matching
        for i in range(len(cjk_buf) - 1):
            tokens.append(cjk_buf[i] + cjk_buf[i + 1])
        cjk_buf.clear()

    for m in re.finditer(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]|[a-zA-Z0-9_]+", text.lower()):
        tok = m.group()
        if len(tok) == 1 and ('\u4e00' <= tok <= '\u9fff'
                              or '\u3400' <= tok <= '\u4dbf'
                              or '\uf900' <= tok <= '\ufaff'):
            cjk_buf.append(tok)
        else:
            _flush_cjk()
            tokens.append(tok)

    _flush_cjk()
    return tokens


def _chunk_text(text: str) -> List[str]:
    """Split *text* into overlapping chunks of ~CHUNK_TARGET_TOKENS tokens."""
    tokens = _rough_tokenize(text)
    if len(tokens) <= CHUNK_TARGET_TOKENS:
        return [text]

    words = text.split()
    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = start + CHUNK_TARGET_TOKENS
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += CHUNK_TARGET_TOKENS - CHUNK_OVERLAP_TOKENS
    return chunks


def _float_list_to_bytes(vec: List[float]) -> bytes:
    """Pack a float list into raw bytes for sqlite-vec."""
    return struct.pack(f"{len(vec)}f", *vec)


def _normalize_scores(scores: Dict[int, float]) -> Dict[int, float]:
    """Normalize scores to [0, 1] range."""
    if not scores:
        return {}
    min_s = min(scores.values())
    max_s = max(scores.values())
    span = max_s - min_s
    if span == 0:
        return {k: 1.0 for k in scores}
    return {k: (v - min_s) / span for k, v in scores.items()}


# ── Store ────────────────────────────────────────────────────────


class DocumentStore:
    """Hybrid BM25 + vector search over indexed text documents.

    The SQLite database stores:
    - ``chunks`` — doc_id, chunk text, tokenised JSON for BM25
    - ``bm25_idf`` — inverse document frequency table
    - ``vec_chunks`` (if sqlite-vec present) — embeddings

    Usage::

        store = DocumentStore("/path/to/index.db")
        store.open()
        store.index_document("my-file.md", text_content)
        results = store.search("relevant query", limit=5)
        store.close()
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._embedder: Any = None
        self._vec_available = False
        self._embed_available = False

    # ── Lifecycle ────────────────────────────────────────────────

    def open(self) -> None:
        """Open or create the database."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")

        try:
            import sqlite_vec  # type: ignore

            sqlite_vec.load(self._conn)
            self._vec_available = True
            logger.debug("sqlite-vec extension loaded")
        except Exception:
            self._vec_available = False
            logger.debug("sqlite-vec not available — vector search disabled")

        self._create_tables()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _ensure_open(self) -> None:
        if self._conn is None:
            self.open()

    # ── Schema ───────────────────────────────────────────────────

    def _create_tables(self) -> None:
        assert self._conn is not None
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id    TEXT NOT NULL,
                chunk_idx INTEGER NOT NULL,
                content   TEXT NOT NULL,
                tokens    TEXT NOT NULL,
                UNIQUE(doc_id, chunk_idx)
            );

            CREATE TABLE IF NOT EXISTS bm25_idf (
                token     TEXT PRIMARY KEY,
                doc_freq  INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        if self._vec_available:
            try:
                self._conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks "
                    f"USING vec0(embedding float[{_EMBED_DIM}])"
                )
            except Exception as e:
                logger.warning("Could not create vec_chunks table: %s", e)
                self._vec_available = False

        self._conn.commit()

    # ── Indexing ─────────────────────────────────────────────────

    def index_document(self, doc_id: str, text: str) -> int:
        """Index (or re-index) a document. Returns number of chunks created."""
        self._ensure_open()
        assert self._conn is not None

        self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))

        chunks = _chunk_text(text)
        embeddings = self._embed_texts(chunks) if self._vec_available else None

        for idx, chunk in enumerate(chunks):
            tokens = _rough_tokenize(chunk)
            token_json = json.dumps(tokens)

            self._conn.execute(
                "INSERT OR REPLACE INTO chunks (doc_id, chunk_idx, content, tokens) "
                "VALUES (?, ?, ?, ?)",
                (doc_id, idx, chunk, token_json),
            )
            row_id = self._conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            if embeddings is not None and self._vec_available:
                vec_bytes = _float_list_to_bytes(embeddings[idx])
                try:
                    self._conn.execute(
                        "INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)",
                        (row_id, vec_bytes),
                    )
                except Exception as e:
                    logger.debug("vec insert failed: %s", e)

        self._rebuild_idf()
        self._conn.commit()
        return len(chunks)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document and rebuild IDF."""
        self._ensure_open()
        assert self._conn is not None
        self._conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self._rebuild_idf()
        self._conn.commit()

    def _rebuild_idf(self) -> None:
        """Recompute inverse document frequencies."""
        assert self._conn is not None
        self._conn.execute("DELETE FROM bm25_idf")

        rows = self._conn.execute("SELECT tokens FROM chunks").fetchall()
        doc_count = len(rows)
        token_doc_freq: Counter[str] = Counter()

        for (token_json,) in rows:
            unique_tokens = set(json.loads(token_json))
            for t in unique_tokens:
                token_doc_freq[t] += 1

        for token, freq in token_doc_freq.items():
            self._conn.execute(
                "INSERT INTO bm25_idf (token, doc_freq) VALUES (?, ?)",
                (token, freq),
            )

        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('doc_count', ?)",
            (str(doc_count),),
        )

    # ── Search ───────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int = 5,
        mode: str = "hybrid",
        semantic_weight: float = 0.5,
    ) -> List[Tuple[str, str, float]]:
        """Search indexed documents.

        Args:
            query: Free-text query.
            limit: Max results.
            mode: ``"hybrid"`` | ``"semantic"`` | ``"keyword"``.
            semantic_weight: Weight for semantic score in hybrid mode (0–1).

        Returns:
            List of ``(doc_id, content, score)`` tuples, highest score first.
        """
        self._ensure_open()
        assert self._conn is not None

        bm25_scores: Dict[int, float] = {}
        vec_scores: Dict[int, float] = {}

        if mode in ("hybrid", "keyword"):
            bm25_scores = self._bm25_search(query)

        if mode in ("hybrid", "semantic") and self._vec_available:
            vec_scores = self._vector_search(query, limit=limit * 3)

        # Merge scores
        if mode == "hybrid" and vec_scores:
            all_ids = set(bm25_scores) | set(vec_scores)
            bm25_norm = _normalize_scores(bm25_scores)
            vec_norm = _normalize_scores(vec_scores)
            kw = 1.0 - semantic_weight
            sw = semantic_weight
            merged = {
                rid: kw * bm25_norm.get(rid, 0.0) + sw * vec_norm.get(rid, 0.0)
                for rid in all_ids
            }
        elif vec_scores:
            merged = vec_scores
        else:
            merged = bm25_scores

        top_ids = sorted(merged, key=lambda k: merged[k], reverse=True)[:limit]
        results: List[Tuple[str, str, float]] = []
        for rid in top_ids:
            row = self._conn.execute(
                "SELECT doc_id, content FROM chunks WHERE id = ?", (rid,)
            ).fetchone()
            if row:
                results.append((row[0], row[1], merged[rid]))

        return results

    def _bm25_search(self, query: str) -> Dict[int, float]:
        """Return ``{chunk_id: bm25_score}`` for the query."""
        assert self._conn is not None
        query_tokens = _rough_tokenize(query)
        if not query_tokens:
            return {}

        meta_row = self._conn.execute(
            "SELECT value FROM meta WHERE key='doc_count'"
        ).fetchone()
        n = int(meta_row[0]) if meta_row else 1

        # IDF for query tokens
        idf_map: Dict[str, float] = {}
        for qt in set(query_tokens):
            row = self._conn.execute(
                "SELECT doc_freq FROM bm25_idf WHERE token = ?", (qt,)
            ).fetchone()
            df = row[0] if row else 0
            idf_map[qt] = math.log((n - df + 0.5) / (df + 0.5) + 1.0)

        # Score each chunk
        scores: Dict[int, float] = {}
        k1, b = 1.5, 0.75

        rows = self._conn.execute("SELECT id, tokens FROM chunks").fetchall()
        avg_dl = sum(len(json.loads(t)) for _, t in rows) / max(len(rows), 1)

        for chunk_id, token_json in rows:
            tokens = json.loads(token_json)
            dl = len(tokens)
            freq = Counter(tokens)
            score = 0.0
            for qt in query_tokens:
                if qt not in idf_map:
                    continue
                tf = freq.get(qt, 0)
                num = tf * (k1 + 1)
                den = tf + k1 * (1 - b + b * dl / avg_dl)
                score += idf_map[qt] * (num / den)
            if score > 0:
                scores[chunk_id] = score

        return scores

    def _vector_search(self, query: str, limit: int = 15) -> Dict[int, float]:
        """Return ``{chunk_id: similarity}`` using sqlite-vec."""
        assert self._conn is not None
        embeddings = self._embed_texts([query])
        if embeddings is None:
            return {}

        qvec = _float_list_to_bytes(embeddings[0])
        try:
            rows = self._conn.execute(
                "SELECT rowid, distance FROM vec_chunks "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (qvec, limit),
            ).fetchall()
        except Exception as e:
            logger.debug("vec search failed: %s", e)
            return {}

        return {rid: 1.0 / (1.0 + dist) for rid, dist in rows}

    # ── Embeddings ───────────────────────────────────────────────

    def _embed_texts(self, texts: List[str]) -> Optional[List[List[float]]]:
        """Embed a batch of texts. Returns ``None`` if unavailable."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore

                self._embedder = SentenceTransformer(_EMBED_MODEL_NAME)
                self._embed_available = True
                logger.info("Loaded embedding model: %s", _EMBED_MODEL_NAME)
            except ImportError:
                self._embed_available = False
                logger.debug(
                    "sentence-transformers not available — vector search disabled"
                )
                return None

        try:
            vecs = self._embedder.encode(texts, show_progress_bar=False)
            return [v.tolist() for v in vecs]
        except Exception as e:
            logger.warning("Embedding failed: %s", e)
            return None
