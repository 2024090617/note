from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from .embedder import Embedder, get_embedder
from .settings import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class NotebookStore:
    def __init__(self, client: QdrantClient, collection: str, embedder: Embedder):
        self._client = client
        self._collection = collection
        self._embedder = embedder

    @property
    def collection(self) -> str:
        return self._collection

    def ensure_collection(self) -> None:
        if self._client.collection_exists(self._collection):
            return

        test = self._embedder.embed(["init"])
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=qm.VectorParams(size=test.dim, distance=qm.Distance.COSINE),
        )

        self._client.create_payload_index(
            collection_name=self._collection,
            field_name="note_id",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )
        self._client.create_payload_index(
            collection_name=self._collection,
            field_name="tags",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )
        self._client.create_payload_index(
            collection_name=self._collection,
            field_name="status",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )

    def upsert_note_version(
        self,
        *,
        note_id: str,
        title: str,
        content: str,
        tags: List[str] | None,
        source_url: str | None,
        status: str,
        verified_at: str | None,
        version: int,
        attachments: List[Dict[str, Any]] | None = None,
    ) -> str:
        self.ensure_collection()

        embedding = self._embedder.embed([f"{title}\n\n{content}"])
        point_id = str(uuid.uuid4())
        payload: Dict[str, Any] = {
            "note_id": note_id,
            "version": version,
            "title": title,
            "content": content,
            "tags": tags or [],
            "source_url": source_url,
            "status": status,
            "created_at": _utc_now_iso(),
            "verified_at": verified_at,
            "attachments": attachments or [],
        }

        self._client.upsert(
            collection_name=self._collection,
            points=[
                qm.PointStruct(
                    id=point_id,
                    vector=embedding.vectors[0],
                    payload=payload,
                )
            ],
        )
        return point_id

    def get_latest_version(self, note_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_collection()
        hits, _ = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="note_id", match=qm.MatchValue(value=note_id))]
            ),
            limit=100,
            with_payload=True,
            with_vectors=False,  # Don't fetch vectors
        )
        if not hits:
            return None
        latest = max(hits, key=lambda p: int(p.payload.get("version", 0)))
        return {"point_id": str(latest.id), **(latest.payload or {})}

    def list_versions(self, note_id: str) -> List[Dict[str, Any]]:
        self.ensure_collection()
        hits, _ = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="note_id", match=qm.MatchValue(value=note_id))]
            ),
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        versions = [{"point_id": str(p.id), **(p.payload or {})} for p in hits]
        versions.sort(key=lambda x: int(x.get("version", 0)), reverse=True)
        return versions

    def search(self, query: str, limit: int = 10, tags: List[str] | None = None) -> List[Dict[str, Any]]:
        self.ensure_collection()
        emb = self._embedder.embed([query])

        flt: qm.Filter | None = None
        if tags:
            flt = qm.Filter(must=[qm.FieldCondition(key="tags", match=qm.MatchAny(any=tags))])

        search_req = qm.SearchRequest(
            vector=emb.vectors[0],
            limit=limit,
            filter=flt,
            with_payload=True,
            with_vector=False,
        )

        resp = self._client.http.search_api.search_points(
            collection_name=self._collection,
            search_request=search_req,
        )
        hits = resp.result or []
        return [
            {
                "score": h.score,
                "point_id": str(h.id),
                **(h.payload or {}),
            }
            for h in hits
        ]

    def delete_note(self, note_id: str) -> int:
        self.ensure_collection()
        hits, _ = self._client.scroll(
            collection_name=self._collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="note_id", match=qm.MatchValue(value=note_id))]
            ),
            limit=1000,
            with_payload=False,
            with_vectors=False,
        )
        if not hits:
            return 0
        
        point_ids = [str(p.id) for p in hits]
        self._client.delete(
            collection_name=self._collection,
            points_selector=qm.PointIdsList(points=point_ids),
        )
        return len(point_ids)

    def list_all_notes(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get latest version of all notes (optimized)"""
        self.ensure_collection()
        
        # Strategy: Scroll efficiently and deduplicate
        notes_by_id = {}
        offset = None
        max_iterations = 20  # Safety limit
        
        for _ in range(max_iterations):
            hits, offset = self._client.scroll(
                collection_name=self._collection,
                limit=100,  # Process in batches
                offset=offset,
                with_payload=True,
                with_vectors=False,  # Don't fetch vectors (saves bandwidth)
            )
            
            if not hits:
                break
            
            # Track latest version per note_id
            for point in hits:
                payload = point.payload or {}
                note_id = payload.get("note_id")
                version = payload.get("version", 0)
                
                if note_id not in notes_by_id or version > notes_by_id[note_id].get("version", 0):
                    notes_by_id[note_id] = {
                        "point_id": str(point.id),
                        **payload
                    }
            
            # Stop if we have enough unique notes
            if len(notes_by_id) >= limit and offset is None:
                break
        
        # Return sorted by created_at
        notes = list(notes_by_id.values())
        notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return notes[:limit]
        
        point_ids = [str(p.id) for p in hits]
        self._client.delete(
            collection_name=self._collection,
            points_selector=qm.PointIdsList(points=point_ids),
        )
        return len(point_ids)


_client_instance = None
_embedder_instance = None


def get_store() -> NotebookStore:
    global _client_instance, _embedder_instance
    
    # Reuse client instance (connection pooling)
    if _client_instance is None:
        _client_instance = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            check_compatibility=False,
            trust_env=False,
            timeout=30,  # Increase timeout
            prefer_grpc=False,  # Use HTTP for better compatibility
        )
    
    # Reuse embedder instance
    if _embedder_instance is None:
        _embedder_instance = get_embedder()
    
    return NotebookStore(client=_client_instance, collection=settings.qdrant_collection, embedder=_embedder_instance)
