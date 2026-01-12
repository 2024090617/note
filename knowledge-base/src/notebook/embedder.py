from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .settings import settings


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: List[List[float]]
    dim: int


class Embedder:
    def embed(self, texts: List[str]) -> EmbeddingResult:
        raise NotImplementedError


class LocalSentenceTransformersEmbedder(Embedder):
    _model_cache = {}  # Class-level cache
    
    def __init__(self, model_name: str):
        # Reuse cached model if available
        if model_name in LocalSentenceTransformersEmbedder._model_cache:
            self._model = LocalSentenceTransformersEmbedder._model_cache[model_name]
            return
        
        from sentence_transformers import SentenceTransformer
        import os
        
        # Force using local cached model, don't check HuggingFace
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        
        self._model = SentenceTransformer(
            model_name,
            local_files_only=True,  # Don't download, use cache only
            trust_remote_code=False
        )
        
        # Cache for reuse
        LocalSentenceTransformersEmbedder._model_cache[model_name] = self._model

    def embed(self, texts: List[str]) -> EmbeddingResult:
        vectors = self._model.encode(texts, normalize_embeddings=True).tolist()
        dim = len(vectors[0]) if vectors else 0
        return EmbeddingResult(vectors=vectors, dim=dim)

def get_embedder() -> Embedder:
    provider = settings.embedding_provider
    return LocalSentenceTransformersEmbedder(settings.local_embedding_model)
