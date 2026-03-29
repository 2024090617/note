"""Tests for digimate.memory.store — BM25 DocumentStore."""

import json
import os
import tempfile

import pytest

from digimate.memory.store import (
    DocumentStore,
    _chunk_text,
    _normalize_scores,
    _rough_tokenize,
)


# ── Helper tokenizer / chunker tests ────────────────────────────


def test_rough_tokenize():
    tokens = _rough_tokenize("Hello, World! This is a test.")
    assert tokens == ["hello", "world", "this", "is", "a", "test"]


def test_rough_tokenize_empty():
    assert _rough_tokenize("") == []


def test_chunk_text_short():
    """Short text should return a single chunk (the original)."""
    text = "hello world foo bar"
    chunks = _chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_long():
    """Text longer than CHUNK_TARGET_TOKENS should produce multiple chunks."""
    words = [f"word{i}" for i in range(800)]
    text = " ".join(words)
    chunks = _chunk_text(text)
    assert len(chunks) > 1
    # Every word should appear in at least one chunk
    all_text = " ".join(chunks)
    for w in words:
        assert w in all_text


def test_normalize_scores_empty():
    assert _normalize_scores({}) == {}


def test_normalize_scores_single():
    assert _normalize_scores({1: 5.0}) == {1: 1.0}


def test_normalize_scores_range():
    result = _normalize_scores({1: 0.0, 2: 10.0, 3: 5.0})
    assert result[1] == pytest.approx(0.0)
    assert result[2] == pytest.approx(1.0)
    assert result[3] == pytest.approx(0.5)


# ── DocumentStore BM25 tests ────────────────────────────────────


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = DocumentStore(db_path)
    s.open()
    yield s
    s.close()


def test_index_and_search(store: DocumentStore):
    store.index_document("doc1", "Python is a great programming language")
    store.index_document("doc2", "JavaScript runs in the browser")
    store.index_document("doc3", "Python and JavaScript are both popular")

    results = store.search("Python programming", limit=3, mode="keyword")
    assert len(results) > 0
    doc_ids = [r[0] for r in results]
    assert "doc1" in doc_ids


def test_search_empty_store(store: DocumentStore):
    results = store.search("anything", mode="keyword")
    assert results == []


def test_search_empty_query(store: DocumentStore):
    store.index_document("doc1", "some content here")
    results = store.search("", mode="keyword")
    assert results == []


def test_reindex_replaces(store: DocumentStore):
    store.index_document("doc1", "original content about cats")
    store.index_document("doc1", "replacement content about dogs")

    results = store.search("cats", mode="keyword")
    # "cats" should no longer match since doc was replaced
    cat_docs = [r for r in results if "cats" in r[1]]
    assert len(cat_docs) == 0

    results = store.search("dogs", mode="keyword")
    assert len(results) > 0
    assert results[0][0] == "doc1"


def test_remove_document(store: DocumentStore):
    store.index_document("doc1", "unique elephant content")
    results = store.search("elephant", mode="keyword")
    assert len(results) == 1

    store.remove_document("doc1")
    results = store.search("elephant", mode="keyword")
    assert len(results) == 0


def test_close_and_reopen(tmp_path):
    db_path = str(tmp_path / "persist.db")
    s = DocumentStore(db_path)
    s.open()
    s.index_document("doc1", "persistent data about quantum physics")
    s.close()

    # Reopen and verify data persists
    s2 = DocumentStore(db_path)
    s2.open()
    results = s2.search("quantum", mode="keyword")
    assert len(results) == 1
    assert results[0][0] == "doc1"
    s2.close()


def test_bm25_score_ordering(store: DocumentStore):
    """Document with more query term occurrences should score higher."""
    store.index_document("low", "The cat sat on a mat")
    store.index_document("high", "Python Python Python is great for Python development")

    results = store.search("Python", mode="keyword")
    assert len(results) >= 1
    assert results[0][0] == "high"


def test_hybrid_falls_back_to_keyword(store: DocumentStore):
    """Hybrid mode without sqlite-vec should fall back to BM25."""
    store.index_document("doc1", "testing hybrid search fallback behavior")
    results = store.search("hybrid search", limit=3, mode="hybrid")
    assert len(results) > 0
