"""Data models for thesis writing agent."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class CitationStyle(str, Enum):
    """Citation style options."""
    
    GB_T_7714 = "GB/T 7714-2015"  # Chinese national standard
    APA = "APA"
    IEEE = "IEEE"
    MLA = "MLA"
    CHICAGO = "Chicago"


class PaperMetadata(BaseModel):
    """Metadata for an academic paper."""
    
    title: str
    title_cn: Optional[str] = None
    title_en: Optional[str] = None
    
    authors: List[str]
    authors_cn: Optional[List[str]] = None
    authors_en: Optional[List[str]] = None
    
    abstract: str
    abstract_cn: Optional[str] = None
    abstract_en: Optional[str] = None
    
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
    
    # Full citation
    bibtex: Optional[str] = None
    
    # Content
    pdf_url: Optional[str] = None
    source_url: Optional[str] = None
    
    # Language
    language: str = "en"  # "en", "zh", "bilingual"
    
    # Tags for organization
    tags: List[str] = Field(default_factory=list)
    
    # Additional metadata
    keywords: List[str] = Field(default_factory=list)
    tldr: Optional[str] = None  # Short summary


class ThesisSection(BaseModel):
    """A section of the thesis."""
    
    section_id: str  # e.g., "1.1", "2.3.1"
    title: str  # e.g., "研究背景"
    title_en: Optional[str] = None
    
    content: str  # Main text content
    
    # Citations used in this section
    citations: List[str] = Field(default_factory=list)  # List of citation keys [1], [2], etc.
    
    # Metadata
    word_count: int = 0
    generated_at: Optional[str] = None
    
    # Writing context
    outline_context: Optional[str] = None  # Related outline section
    requirements: Optional[str] = None  # User requirements for this section


class ThesisOutline(BaseModel):
    """Thesis outline structure."""
    
    title: str
    title_en: Optional[str] = None
    
    # Hierarchical structure
    chapters: List[Dict[str, Any]] = Field(default_factory=list)
    # Example structure:
    # [
    #   {
    #     "number": "第一章",
    #     "title": "绪论",
    #     "sections": [
    #       {"number": "1.1", "title": "研究背景"},
    #       {"number": "1.2", "title": "研究意义"}
    #     ]
    #   }
    # ]
    
    # Metadata
    total_chapters: int = 0
    total_sections: int = 0
    estimated_words: int = 0
    
    # Requirements
    requirements: Optional[str] = None


class FormattingRules(BaseModel):
    """Document formatting rules interpreted from natural language."""
    
    # Page setup
    page_size: str = "A4"  # "A4", "Letter"
    page_margins: Dict[str, str] = Field(
        default_factory=lambda: {
            "top": "2.54cm",
            "bottom": "2.54cm",
            "left": "3.17cm",
            "right": "3.17cm"
        }
    )
    
    # Fonts
    body_font: Dict[str, str] = Field(
        default_factory=lambda: {
            "chinese": "宋体",  # SimSun
            "english": "Times New Roman"
        }
    )
    body_font_size: str = "12pt"  # "小四" in Chinese
    
    heading_fonts: Dict[str, Dict[str, str]] = Field(
        default_factory=lambda: {
            "level1": {"chinese": "黑体", "english": "Arial", "size": "18pt"},  # 一级标题
            "level2": {"chinese": "黑体", "english": "Arial", "size": "16pt"},  # 二级标题
            "level3": {"chinese": "黑体", "english": "Arial", "size": "14pt"},  # 三级标题
        }
    )
    
    # Spacing
    line_spacing: float = 1.5
    paragraph_spacing_before: str = "0pt"
    paragraph_spacing_after: str = "0pt"
    first_line_indent: str = "2em"  # 首行缩进
    
    # Alignment
    body_alignment: str = "justified"  # "left", "center", "right", "justified"
    heading_alignment: str = "left"
    
    # Citation
    citation_style: CitationStyle = CitationStyle.GB_T_7714
    
    # TOC (Table of Contents)
    include_toc: bool = True
    toc_title: str = "目录"
    toc_title_en: Optional[str] = "Table of Contents"
    
    # References
    references_title: str = "参考文献"
    references_title_en: Optional[str] = "References"
    
    # Page numbering
    page_number_position: str = "bottom-center"  # "top-right", "bottom-center", etc.
    page_number_start: int = 1
    
    # Header/Footer
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    
    # Additional Chinese-specific settings
    chinese_punctuation: bool = True  # Use Chinese punctuation (，。！？)
    
    # Original user specification
    user_specification: Optional[str] = None


class ThesisConfig(BaseModel):
    """Configuration for thesis writing project."""
    
    title: str
    title_en: Optional[str] = None
    
    author: str
    author_en: Optional[str] = None
    
    institution: str
    institution_en: Optional[str] = None
    
    degree: str = "硕士"  # 硕士/博士
    major: Optional[str] = None
    
    advisor: Optional[str] = None
    advisor_en: Optional[str] = None
    
    date: Optional[str] = None
    
    # Formatting
    formatting_spec: str = "标准中国高校硕士学位论文"
    
    # Output
    output_dir: str = "./thesis_output"
    sections_dir: str = "./sections"
    
    # Research
    research_keywords: List[str] = Field(default_factory=list)
    min_papers: int = 20
    max_papers: int = 100
