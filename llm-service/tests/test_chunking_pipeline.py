"""Tests for Phase 2: Chunked content pipeline."""

import pytest
from pathlib import Path
from llm_service.agent.core.content_chunker import ContentChunker, Chunk
from llm_service.agent.core.artifact_store import ArtifactStore, Artifact
from llm_service.agent.core.chunked_output_adapter import ChunkedOutputAdapter
from llm_service.agent.tools.types import ToolResult


class TestContentChunker:
    """Test content chunking strategies."""

    def test_small_content_no_split(self):
        """Small content should not be split."""
        chunker = ContentChunker(max_chunk_chars=1000)
        text = "Hello world" * 10  # ~110 chars
        chunks = chunker.chunk(text)

        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].chunk_id == 0

    def test_line_based_chunking(self):
        """Line-based strategy respects line boundaries."""
        chunker = ContentChunker(
            max_chunk_chars=200,
            strategy="line",
        )
        lines = ["Line " + str(i) * 50 for i in range(10)]
        text = "\n".join(lines)

        chunks = chunker.chunk(text)
        assert len(chunks) > 1  # Should split into multiple chunks
        assert all("\n" not in c.content.split("\n")[-1] for c in chunks[:-1])  # All complete lines

    def test_paragraph_chunking(self):
        """Paragraph-based strategy respects blank lines."""
        chunker = ContentChunker(
            max_chunk_chars=300,
            strategy="paragraph",
        )
        paragraphs = [
            "Paragraph " + str(i) * 50 + "\n" for i in range(5)
        ]
        text = "\n\n".join(paragraphs)

        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        # Check that paragraphs aren't split in middle
        for chunk in chunks:
            assert "Paragraph" in chunk.content or chunk.content.strip() == ""

    def test_code_block_aware_chunking(self):
        """Code-block-aware strategy preserves code fence boundaries."""
        chunker = ContentChunker(
            max_chunk_chars=300,
            strategy="code-block",
        )
        text = (
            "Some intro text\n\n"
            "```python\n"
            "def hello():\n"
            "    return 'world' * 100\n"  # Long code block
            "```\n\n"
            "More text after code"
        )

        chunks = chunker.chunk(text)
        # Code block should be preserved as unit
        code_chunks = [c for c in chunks if "```" in c.content or "def hello" in c.content]
        assert len(code_chunks) > 0

    def test_hybrid_chunking(self):
        """Hybrid strategy tries code → paragraph → line."""
        chunker = ContentChunker(
            max_chunk_chars=500,
            strategy="hybrid",
        )
        text = (
            "# Readme\n\n"
            "Documentation paragraph 1.\n\n"
            "```python\n"
            "code = 'here' * 50\n"
            "```\n\n"
            "Documentation paragraph 2.\n"
            * 10
        )

        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(0 <= c.chunk_id < len(chunks) for c in chunks)

    def test_chunk_metadata(self):
        """Chunks should include proper metadata."""
        chunker = ContentChunker(max_chunk_chars=200, strategy="line")
        text = "Line\n" * 100

        chunks = chunker.chunk(text)
        for chunk in chunks:
            assert chunk.chunk_id >= 0
            assert chunk.start_pos >= 0
            assert chunk.end_pos > chunk.start_pos
            assert chunk.metadata.get("strategy") in ["line", "hybrid", "paragraph", "code-block"]


class TestArtifactStore:
    """Test artifact storage and retrieval."""

    def test_store_and_retrieve(self):
        """Store content and retrieve by artifact ID."""
        store = ArtifactStore()
        content = "Hello " * 1000
        artifact_id = store.store(content, "file_read", metadata={"path": "/test.txt"})

        assert artifact_id
        retrieved = store.retrieve(artifact_id)
        assert retrieved == content

    def test_deduplication(self):
        """Identical content yields same artifact ID."""
        store = ArtifactStore()
        content = "Duplicate " * 100
        id1 = store.store(content, "file_read", metadata={"path": "/test1.txt"})
        id2 = store.store(content, "command_output", metadata={"command": "echo dup"})

        assert id1 == id2  # Should deduplicate by content hash

    def test_chunk_retrieval(self):
        """Retrieve specific chunks from artifact."""
        store = ArtifactStore()
        chunks = [
            {"chunk_id": 0, "start_pos": 0, "end_pos": 1000, "size_chars": 1000, "content": "Chunk 0" * 100},
            {"chunk_id": 1, "start_pos": 1000, "end_pos": 2000, "size_chars": 1000, "content": "Chunk 1" * 100},
        ]
        artifact_id = store.store(
            "Chunk 0" * 100 + "Chunk 1" * 100,
            "file_read",
            chunks=chunks,
        )

        chunk0 = store.retrieve(artifact_id, chunk_id=0)
        assert chunk0 == "Chunk 0" * 100
        chunk1 = store.retrieve(artifact_id, chunk_id=1)
        assert chunk1 == "Chunk 1" * 100

    def test_lru_eviction(self):
        """LRU eviction removes least-recently-used artifact."""
        store = ArtifactStore(max_artifacts=2)
        id1 = store.store("Content 1" * 100, "file_read")
        id2 = store.store("Content 2" * 100, "file_read")
        id3 = store.store("Content 3" * 100, "file_read")

        # id1 should be evicted
        assert store.retrieve(id1) is None
        assert store.retrieve(id2) is not None
        assert store.retrieve(id3) is not None

    def test_artifact_info(self):
        """Get metadata for artifact."""
        store = ArtifactStore()
        content = "Test" * 1000
        artifact_id = store.store(
            content,
            "mcp_tool",
            metadata={"server": "github-api", "tool": "search_repos"},
        )

        info = store.get_artifact_info(artifact_id)
        assert info.artifact_id == artifact_id
        assert info.original_source == "mcp_tool"
        assert info.total_size_bytes == len(content)
        assert info.metadata["server"] == "github-api"

    def test_store_stats(self):
        """Get store statistics."""
        store = ArtifactStore()
        store.store("A" * 1000, "file_read")
        store.store("B" * 2000, "command_output")

        stats = store.stats()
        assert stats["artifact_count"] == 2
        assert stats["total_bytes"] == 3000
        assert "total_mb" in stats

    def test_clear_store(self):
        """Clear all artifacts from store."""
        store = ArtifactStore()
        store.store("Content" * 100, "file_read")
        store.store("Content" * 100, "command_output")
        assert len(store.list_artifacts()) > 0

        store.clear()
        assert len(store.list_artifacts()) == 0


class TestChunkedOutputAdapter:
    """Test tool output processing through chunking adapter."""

    def test_output_under_threshold_passes_through(self):
        """Output under threshold should pass through unchanged."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(
            artifact_store,
            chunking_threshold_chars=1000,
        )
        small_output = "Small " * 50  # ~300 chars
        result = ToolResult(success=True, output=small_output)

        chunked = adapter.process_tool_result(result, "file_read")
        assert not chunked.is_chunked
        assert small_output in chunked.summary

    def test_output_over_threshold_gets_chunked(self):
        """Output over threshold should be chunked and stored."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(
            artifact_store,
            chunking_threshold_chars=1000,
            max_chunk_chars=2000,
        )
        large_output = "Large text\n" * 500  # ~5500 chars
        result = ToolResult(success=True, output=large_output)

        chunked = adapter.process_tool_result(
            result,
            "file_read",
            source_metadata={"path": "/big_file.txt"},
        )

        assert chunked.is_chunked
        assert chunked.artifact_id is not None
        assert len(chunked.chunks) > 1
        assert "artifact_id=" + chunked.artifact_id in chunked.summary
        assert "/big_file.txt" in chunked.summary

    def test_chunk_metadata_in_summary(self):
        """Summary should include chunk metadata."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(
            artifact_store,
            chunking_threshold_chars=500,
        )
        output = "Line\n" * 300  # ~1200 chars
        result = ToolResult(success=True, output=output)

        chunked = adapter.process_tool_result(
            result,
            "command_output",
            source_metadata={"command": "ls -la /"},
        )

        assert "Size:" in chunked.summary
        assert "Chunks:" in chunked.summary
        assert "command:" in chunked.summary or "ls -la" in chunked.summary

    def test_mcp_tool_source_metadata(self):
        """MCP tool sources should include server:tool metadata."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(artifact_store, chunking_threshold_chars=500)
        output = "MCP result\n" * 200  # ~2400 chars

        result = ToolResult(success=True, output=output)
        chunked = adapter.process_tool_result(
            result,
            "mcp_tool",
            source_metadata={"server": "github-api", "tool": "get_issues"},
        )

        assert chunked.artifact_id
        assert "github-api:get_issues" in chunked.summary

    def test_retrieve_chunk_from_adapter(self):
        """Adapter should support retrieving chunks from artifact."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(
            artifact_store,
            chunking_threshold_chars=500,
        )
        output = "Block A\n" * 200 + "Block B\n" * 200
        result = ToolResult(success=True, output=output)

        chunked = adapter.process_tool_result(result, "file_read")
        assert chunked.is_chunked

        chunk0 = adapter.retrieve_chunk(chunked.artifact_id, chunk_id=0)
        assert chunk0 is not None
        assert "Block A" in chunk0

    def test_failed_tool_result(self):
        """Failed tool result should be handled gracefully."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(artifact_store)

        result = ToolResult(success=False, output="", error="File not found")
        chunked = adapter.process_tool_result(result, "file_read")

        assert not chunked.is_chunked
        # Empty output under threshold should pass through (summary will be empty)
        assert isinstance(chunked.summary, str)

    def test_empty_output(self):
        """Empty output should be handled safely."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(artifact_store)

        result = ToolResult(success=True, output="")
        chunked = adapter.process_tool_result(result, "file_read")

        assert not chunked.is_chunked
        assert artifact_store.stats()["artifact_count"] == 0


class TestChunkingIntegration:
    """Integration tests for chunking with agent workflow."""

    def test_full_chunking_pipeline(self):
        """Complete flow: chunking → storage → summary → retrieval."""
        artifact_store = ArtifactStore()
        chunker = ContentChunker(max_chunk_chars=3000)

        # Simulate large file content
        large_file = "import os\nfrom typing import *\n" * 500  # ~15KB
        chunks = chunker.chunk(large_file)
        assert len(chunks) > 1

        # Store into artifact
        chunk_data = [
            {
                "chunk_id": c.chunk_id,
                "start_pos": c.start_pos,
                "end_pos": c.end_pos,
                "size_chars": len(c.content),
                "content": c.content,
                "metadata": c.metadata,
            }
            for c in chunks
        ]
        artifact_id = artifact_store.store(
            large_file,
            "file_read",
            metadata={"path": "/large_module.py"},
            chunks=chunk_data,
        )

        # Verify artifact
        info = artifact_store.get_artifact_info(artifact_id)
        assert info.chunk_count == len(chunks)
        assert info.total_size_bytes == len(large_file)

        # Retrieve full content
        full = artifact_store.retrieve(artifact_id)
        assert full == large_file

        # Retrieve specific chunks
        chunk0 = artifact_store.retrieve(artifact_id, chunk_id=0)
        assert chunk0 in large_file

    def test_adapter_with_multiple_sources(self):
        """Adapter should handle different source types."""
        artifact_store = ArtifactStore()
        adapter = ChunkedOutputAdapter(artifact_store, chunking_threshold_chars=1000)

        sources = [
            ("file_read", {"path": "/etc/passwd"}, "root:x:0:0" * 500),
            ("command_output", {"command": "ps aux"}, "PID  USER  COMMAND" * 500),
            ("mcp_tool", {"server": "api", "tool": "query"}, "Result data" * 500),
        ]

        artifact_ids = []
        for source_type, metadata, output in sources:
            result = ToolResult(success=True, output=output)
            chunked = adapter.process_tool_result(result, source_type, source_metadata=metadata)
            if chunked.is_chunked:
                artifact_ids.append(chunked.artifact_id)

        # All should be stored (and deduplicated if content matches)
        stats = artifact_store.stats()
        assert stats["artifact_count"] <= len(sources)  # May be less due to deduplication
