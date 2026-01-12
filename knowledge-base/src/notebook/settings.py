from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel

try:
    from dotenv import load_dotenv

    # Load from project root .env (knowledge-base/.env)
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")
except Exception:
    # Optional: allow running without python-dotenv
    pass


class Settings(BaseModel):
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str | None = os.getenv("QDRANT_API_KEY") or None
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "notebook")

    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local").lower()
    local_embedding_model: str = os.getenv(
        "LOCAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
    )

settings = Settings()
