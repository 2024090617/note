"""Content chunking and semantic split strategies."""

import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class Chunk:
    """A semantic unit of content."""

    content: str
    chunk_id: int
    start_pos: int  # character offset in original
    end_pos: int    # character offset in original
    metadata: Dict[str, Any]  # e.g., {"type": "code_block", "language": "python"}


class ContentChunker:
    """
    Splits large text content into manageable chunks using semantic boundaries.
    
    Strategies:
    - line-based: Split on newlines, respecting min/max chunk sizes
    - paragraph-based: Split on blank lines (natural paragraph boundaries)
    - code-block-aware: Respect code fence boundaries (```), preserve indentation context
    - hybrid: Combine strategies (paragraph → code blocks → lines if needed)
    """

    def __init__(
        self,
        min_chunk_chars: int = 500,
        max_chunk_chars: int = 4000,
        overlap_chars: int = 200,
        strategy: str = "hybrid",
    ):
        """
        Initialize chunker.

        Args:
            min_chunk_chars: Minimum chunk size before merging with adjacent
            max_chunk_chars: Maximum chunk size before force-splitting
            overlap_chars: Characters to overlap between chunks for context preservation
            strategy: "line" | "paragraph" | "code-block" | "hybrid"
        """
        self.min_chunk_chars = min_chunk_chars
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars
        self.strategy = strategy

    def chunk(self, text: str) -> List[Chunk]:
        """
        Split text into semantic chunks.

        Args:
            text: Input text content

        Returns:
            List of Chunk objects
        """
        if len(text) <= self.max_chunk_chars:
            return [
                Chunk(
                    content=text,
                    chunk_id=0,
                    start_pos=0,
                    end_pos=len(text),
                    metadata={"strategy": "no_split"},
                )
            ]

        if self.strategy == "hybrid":
            return self._chunk_hybrid(text)
        elif self.strategy == "code-block":
            return self._chunk_code_block_aware(text)
        elif self.strategy == "paragraph":
            return self._chunk_paragraph(text)
        else:  # line-based
            return self._chunk_line(text)

    def _chunk_hybrid(self, text: str) -> List[Chunk]:
        """
        Hybrid strategy: try code-block → paragraph → line splits in order.
        """
        # Try code-block aware first
        chunks = self._chunk_code_block_aware(text)
        if len(chunks) > 1 and max(len(c.content) for c in chunks) <= self.max_chunk_chars:
            return chunks

        # If any chunk still too large, fall back to paragraph
        chunks = self._chunk_paragraph(text)
        if len(chunks) > 1 and max(len(c.content) for c in chunks) <= self.max_chunk_chars:
            return chunks

        # Final fallback to line-based
        return self._chunk_line(text)

    def _chunk_code_block_aware(self, text: str) -> List[Chunk]:
        """
        Split respecting code fence boundaries (```).
        Keeps code blocks intact, splits markdown prose at paragraphs.
        """
        chunks = []
        in_code_block = False
        current_chunk = ""
        chunk_id = 0
        start_pos = 0

        for i, line in enumerate(text.split("\n")):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            current_chunk += line + "\n"

            # Decide when to finalize chunk
            should_split = False

            if in_code_block:
                # Inside code: only split if hitting max size
                should_split = len(current_chunk) >= self.max_chunk_chars
            else:
                # Outside code: split at blank lines or max size
                is_blank = line.strip() == ""
                should_split = (
                    is_blank and len(current_chunk) >= self.min_chunk_chars
                ) or (len(current_chunk) >= self.max_chunk_chars)

            if should_split and current_chunk:
                chunks.append(
                    Chunk(
                        content=current_chunk.rstrip(),
                        chunk_id=chunk_id,
                        start_pos=start_pos,
                        end_pos=start_pos + len(current_chunk),
                        metadata={"strategy": "code-block-aware"},
                    )
                )
                # Add overlap for context
                if self.overlap_chars > 0:
                    overlap = current_chunk[-self.overlap_chars :] if len(current_chunk) > self.overlap_chars else current_chunk
                    current_chunk = overlap
                    start_pos += len(current_chunk) - len(overlap)
                else:
                    current_chunk = ""
                    start_pos += len(current_chunk)
                chunk_id += 1

        if current_chunk.strip():
            chunks.append(
                Chunk(
                    content=current_chunk.rstrip(),
                    chunk_id=chunk_id,
                    start_pos=start_pos,
                    end_pos=start_pos + len(current_chunk),
                    metadata={"strategy": "code-block-aware"},
                )
            )

        return chunks or [
            Chunk(
                content=text,
                chunk_id=0,
                start_pos=0,
                end_pos=len(text),
                metadata={"strategy": "code-block-aware", "fallback": True},
            )
        ]

    def _chunk_paragraph(self, text: str) -> List[Chunk]:
        """Split at blank-line boundaries (natural paragraphs)."""
        # Split on blank lines
        segments = re.split(r"\n\n+", text)

        chunks = []
        current_chunk = ""
        chunk_id = 0
        start_pos = 0

        for seg in segments:
            if current_chunk and len(current_chunk) + len(seg) > self.max_chunk_chars:
                # Current chunk + this segment would exceed max → finalize
                chunks.append(
                    Chunk(
                        content=current_chunk.rstrip(),
                        chunk_id=chunk_id,
                        start_pos=start_pos,
                        end_pos=start_pos + len(current_chunk),
                        metadata={"strategy": "paragraph"},
                    )
                )
                chunk_id += 1
                current_chunk = seg + "\n\n"
                start_pos += len(current_chunk)
            else:
                current_chunk += seg + "\n\n"

            # If single segment is too large, force split it
            if len(current_chunk) >= self.max_chunk_chars:
                chunks.append(
                    Chunk(
                        content=current_chunk.rstrip(),
                        chunk_id=chunk_id,
                        start_pos=start_pos,
                        end_pos=start_pos + len(current_chunk),
                        metadata={"strategy": "paragraph"},
                    )
                )
                chunk_id += 1
                current_chunk = ""

        if current_chunk.strip():
            chunks.append(
                Chunk(
                    content=current_chunk.rstrip(),
                    chunk_id=chunk_id,
                    start_pos=start_pos,
                    end_pos=start_pos + len(current_chunk),
                    metadata={"strategy": "paragraph"},
                )
            )

        return chunks or [
            Chunk(
                content=text,
                chunk_id=0,
                start_pos=0,
                end_pos=len(text),
                metadata={"strategy": "paragraph", "fallback": True},
            )
        ]

    def _chunk_line(self, text: str) -> List[Chunk]:
        """Split on line boundaries, respecting min/max sizes."""
        lines = text.split("\n")
        chunks = []
        current_chunk = ""
        chunk_id = 0
        start_pos = 0

        for line in lines:
            line_with_newline = line + "\n"

            if current_chunk and len(current_chunk) + len(line_with_newline) >= self.max_chunk_chars:
                chunks.append(
                    Chunk(
                        content=current_chunk.rstrip(),
                        chunk_id=chunk_id,
                        start_pos=start_pos,
                        end_pos=start_pos + len(current_chunk),
                        metadata={"strategy": "line"},
                    )
                )
                chunk_id += 1
                current_chunk = line_with_newline
                start_pos += len(current_chunk)
            else:
                current_chunk += line_with_newline

        if current_chunk.strip():
            chunks.append(
                Chunk(
                    content=current_chunk.rstrip(),
                    chunk_id=chunk_id,
                    start_pos=start_pos,
                    end_pos=start_pos + len(current_chunk),
                    metadata={"strategy": "line"},
                )
            )

        return chunks or [
            Chunk(
                content=text,
                chunk_id=0,
                start_pos=0,
                end_pos=len(text),
                metadata={"strategy": "line", "fallback": True},
            )
        ]
