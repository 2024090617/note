"""Adapter for chunked large-content tool outputs."""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from ..tools.types import ToolResult
from .content_chunker import ContentChunker, Chunk
from .artifact_store import ArtifactStore


@dataclass
class ChunkedOutput:
    """Result of processing a tool output through chunking adapter."""

    is_chunked: bool
    artifact_id: Optional[str]
    chunks: List[Chunk]
    summary: str  # Human-readable summary for agent
    original_output: str  # Original unchunked content
    chunk_metadata: Dict[str, Any]  # Info about chunking decision


class ChunkedOutputAdapter:
    """
    Processes large tool outputs using intelligent chunking.
    
    Strategy:
    1. If output ≤ threshold → pass through unchanged
    2. If output > threshold → chunk, store, return summary + artifact reference
    3. Maintains artifact store for reference-based retrieval
    """

    def __init__(
        self,
        artifact_store: ArtifactStore,
        chunking_threshold_chars: int = 6000,
        min_chunk_chars: int = 500,
        max_chunk_chars: int = 4000,
        chunking_strategy: str = "hybrid",
    ):
        """
        Initialize chunked output adapter.

        Args:
            artifact_store: ArtifactStore instance for storing payloads
            chunking_threshold_chars: Don't chunk unless output exceeds this
            min_chunk_chars: Min chunk size (passed to ContentChunker)
            max_chunk_chars: Max chunk size (passed to ContentChunker)
            chunking_strategy: "hybrid" | "paragraph" | "code-block" | "line"
        """
        self.artifact_store = artifact_store
        self.chunking_threshold_chars = chunking_threshold_chars
        self.chunker = ContentChunker(
            min_chunk_chars=min_chunk_chars,
            max_chunk_chars=max_chunk_chars,
            strategy=chunking_strategy,
        )

    def process_tool_result(
        self,
        tool_result: ToolResult,
        source_type: str,
        source_metadata: Optional[Dict[str, Any]] = None,
    ) -> ChunkedOutput:
        """
        Process a tool result through chunking adapter.

        Args:
            tool_result: ToolResult from tool execution
            source_type: "file_read" | "command_output" | "mcp_tool"
            source_metadata: Optional metadata (e.g., file path, command string)

        Returns:
            ChunkedOutput with decision and summary
        """
        output_text = tool_result.output or ""
        output_size = len(output_text)

        # Decide: chunk or pass through?
        if output_size <= self.chunking_threshold_chars:
            return ChunkedOutput(
                is_chunked=False,
                artifact_id=None,
                chunks=[],
                summary=output_text[:500] + ("..." if len(output_text) > 500 else ""),
                original_output=output_text,
                chunk_metadata={"reason": "under_threshold", "size_chars": output_size},
            )

        # Output is large → chunk it
        chunks = self.chunker.chunk(output_text)
        chunk_data = [
            {
                "chunk_id": c.chunk_id,
                "start_pos": c.start_pos,
                "end_pos": c.end_pos,
                "size_chars": len(c.content),
                "metadata": c.metadata,
                "content": c.content,
            }
            for c in chunks
        ]

        # Store in artifact store
        artifact_id = self.artifact_store.store(
            content=output_text,
            source_type=source_type,
            metadata=source_metadata or {},
            chunks=chunk_data,
        )

        # Generate summary mentioning artifact
        summary = self._generate_summary(
            artifact_id=artifact_id,
            chunks=chunks,
            source_type=source_type,
            source_metadata=source_metadata,
            total_size=output_size,
        )

        return ChunkedOutput(
            is_chunked=True,
            artifact_id=artifact_id,
            chunks=chunks,
            summary=summary,
            original_output=output_text,
            chunk_metadata={
                "reason": "over_threshold",
                "size_chars": output_size,
                "chunk_count": len(chunks),
                "strategy": self.chunker.strategy,
                "artifact_id": artifact_id,
            },
        )

    def _generate_summary(
        self,
        artifact_id: str,
        chunks: List[Chunk],
        source_type: str,
        source_metadata: Optional[Dict[str, Any]],
        total_size: int,
    ) -> str:
        """Generate a human-readable summary for large output."""
        source_desc = source_type.replace("_", " ").title()
        size_mb = round(total_size / (1024 * 1024), 2)
        size_desc = f"{size_mb}MB" if size_mb > 0 else f"{total_size} bytes"

        # Add source-specific context
        source_context = ""
        if source_metadata:
            if "path" in source_metadata:
                source_context = f" ({source_metadata['path']})"
            elif "command" in source_metadata:
                source_context = f" (command: {source_metadata['command'][:50]}...)"
            elif "server" in source_metadata and "tool" in source_metadata:
                source_context = f" ({source_metadata['server']}:{source_metadata['tool']})"

        summary = (
            f"Output truncated: {source_desc}{source_context}\n"
            f"Size: {size_desc} | Chunks: {len(chunks)}\n"
            f"Reference: artifact_id={artifact_id}\n"
            f"\nFirst chunk preview:\n"
            f"{_truncate_preview(chunks[0].content if chunks else '', max_chars=400)}"
        )

        return summary

    def retrieve_chunk(self, artifact_id: str, chunk_id: int) -> Optional[str]:
        """Retrieve a specific chunk by artifact and chunk ID."""
        return self.artifact_store.retrieve(artifact_id, chunk_id=chunk_id)

    def retrieve_full(self, artifact_id: str) -> Optional[str]:
        """Retrieve full original content by artifact ID."""
        return self.artifact_store.retrieve(artifact_id, chunk_id=None)


def _truncate_preview(text: str, max_chars: int = 400, suffix: str = "...") -> str:
    """Truncate text for preview with ellipsis."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + suffix
