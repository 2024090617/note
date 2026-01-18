from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    tags: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None


class PaperCreate(BaseModel):
    """Create a paper entry with academic metadata."""
    
    # Basic info
    title: str = Field(min_length=1, max_length=500)
    title_cn: Optional[str] = None
    title_en: Optional[str] = None
    
    # Content
    content: str = Field(min_length=1)  # Abstract + key sections
    abstract: Optional[str] = None
    abstract_cn: Optional[str] = None
    abstract_en: Optional[str] = None
    
    # Authors
    authors: List[str] = Field(default_factory=list)
    authors_cn: Optional[List[str]] = None
    authors_en: Optional[List[str]] = None
    
    # Identifiers
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    
    # Publication details
    publication_year: int
    publication_venue: Optional[str] = None  # Journal/Conference
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    
    # Metrics
    citation_count: Optional[int] = 0
    
    # Citations
    bibtex: Optional[str] = None
    
    # URLs
    pdf_url: Optional[str] = None
    source_url: Optional[str] = None
    
    # Language
    language: str = "en"  # "en", "zh", "bilingual"
    
    # Tags for organization
    tags: List[str] = Field(default_factory=list)
    
    # Additional metadata
    keywords: List[str] = Field(default_factory=list)
    tldr: Optional[str] = None  # Short summary


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
