"""Artifact store for large content payloads with reference system."""

import hashlib
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Optional, Any, List


@dataclass
class Artifact:
    """A stored large payload with metadata."""

    artifact_id: str
    original_source: str  # "file_read", "command_output", "mcp_tool"
    content_hash: str  # SHA256 hash for deduplication
    total_size_bytes: int
    chunk_count: int
    created_at: str
    metadata: Dict[str, Any]  # source-specific (e.g., file path, command, server:tool)
    chunks: List[Dict[str, Any]] = None  # list of {chunk_id, start_pos, end_pos, summary_tokens}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize artifact metadata."""
        return asdict(self)


class ArtifactStore:
    """
    In-memory store for large content payloads.
    
    Provides:
    - Reference-based access (artifact_id + chunk_id → content)
    - Deduplication by hash
    - Metadata tracking per artifact
    - TTL-based cleanup (optional)
    """

    def __init__(self, max_artifacts: int = 1000):
        """
        Initialize artifact store.

        Args:
            max_artifacts: Max number of artifacts before LRU eviction
        """
        self.max_artifacts = max_artifacts
        self._artifacts: Dict[str, Artifact] = {}  # artifact_id → Artifact metadata
        self._payloads: Dict[str, str] = {}  # artifact_id → full original content
        self._chunks: Dict[str, Dict[int, str]] = {}  # artifact_id → {chunk_id → content}
        self._hash_to_artifact: Dict[str, str] = {}  # content_hash → artifact_id (dedup)
        self._access_order: List[str] = []  # for LRU eviction

    def store(
        self,
        content: str,
        source_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunks: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Store a large payload and return its artifact_id.

        Args:
            content: Full original content
            source_type: "file_read" | "command_output" | "mcp_tool"
            metadata: Source-specific metadata (path, command, server:tool, etc.)
            chunks: List of chunk metadata (from ContentChunker)

        Returns:
            artifact_id (str)
        """
        # Check deduplication
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        if content_hash in self._hash_to_artifact:
            return self._hash_to_artifact[content_hash]

        # Generate artifact ID
        artifact_id = f"{source_type}_{hashlib.sha256((content_hash + str(len(self._artifacts))).encode()).hexdigest()[:12]}"

        chunk_count = len(chunks) if chunks else 1
        artifact = Artifact(
            artifact_id=artifact_id,
            original_source=source_type,
            content_hash=content_hash,
            total_size_bytes=len(content),
            chunk_count=chunk_count,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
            chunks=chunks or [],
        )

        self._artifacts[artifact_id] = artifact
        self._payloads[artifact_id] = content
        self._hash_to_artifact[content_hash] = artifact_id
        self._access_order.append(artifact_id)

        # Initialize chunk storage
        if chunks:
            self._chunks[artifact_id] = {}
            for chunk in chunks:
                chunk_id = chunk.get("chunk_id", 0)
                chunk_content = chunk.get("content", "")
                self._chunks[artifact_id][chunk_id] = chunk_content

        # LRU eviction if needed
        if len(self._artifacts) > self.max_artifacts:
            self._evict_lru()

        return artifact_id

    def retrieve(self, artifact_id: str, chunk_id: Optional[int] = None) -> Optional[str]:
        """
        Retrieve content from artifact.

        Args:
            artifact_id: Artifact ID
            chunk_id: Optional chunk ID (None retrieves all)

        Returns:
            Content string or None if not found
        """
        if artifact_id not in self._artifacts:
            return None

        # Mark as recently accessed
        if artifact_id in self._access_order:
            self._access_order.remove(artifact_id)
        self._access_order.append(artifact_id)

        if chunk_id is None:
            # Return full payload
            return self._payloads.get(artifact_id)
        else:
            # Return specific chunk
            if artifact_id in self._chunks:
                return self._chunks[artifact_id].get(chunk_id)
            return None

    def get_artifact_info(self, artifact_id: str) -> Optional[Artifact]:
        """Get metadata for artifact."""
        return self._artifacts.get(artifact_id)

    def list_artifacts(self) -> List[Artifact]:
        """List all stored artifacts."""
        return list(self._artifacts.values())

    def delete(self, artifact_id: str) -> bool:
        """Delete an artifact."""
        if artifact_id not in self._artifacts:
            return False

        artifact = self._artifacts[artifact_id]
        content_hash = artifact.content_hash

        del self._artifacts[artifact_id]
        del self._payloads[artifact_id]
        if artifact_id in self._chunks:
            del self._chunks[artifact_id]
        if content_hash in self._hash_to_artifact:
            del self._hash_to_artifact[content_hash]
        if artifact_id in self._access_order:
            self._access_order.remove(artifact_id)

        return True

    def clear(self):
        """Clear all artifacts."""
        self._artifacts.clear()
        self._payloads.clear()
        self._chunks.clear()
        self._hash_to_artifact.clear()
        self._access_order.clear()

    def _evict_lru(self):
        """Evict least-recently-used artifact."""
        if self._access_order:
            lru_id = self._access_order.pop(0)
            self.delete(lru_id)

    def stats(self) -> Dict[str, Any]:
        """Return store statistics."""
        total_bytes = sum(len(content) for content in self._payloads.values())
        return {
            "artifact_count": len(self._artifacts),
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "max_artifacts": self.max_artifacts,
        }
