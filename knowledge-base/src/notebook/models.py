from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    tags: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    source_url: Optional[str] = None


class NoteVerify(BaseModel):
    status: str = Field(pattern="^(unverified|verified|needs_review)$")


class NoteMetadataUpdate(BaseModel):
    """Update metadata without changing content"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    tags: Optional[List[str]] = None
    status: Optional[str] = Field(default=None, pattern="^(unverified|verified|needs_review)$")
    source_url: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    tags: List[str] = Field(default_factory=list)
