"""Thesis writing agent with RAG capabilities."""

import sys
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

# Add knowledge-base to path
kb_path = Path(__file__).parent.parent.parent.parent / "knowledge-base" / "src"
sys.path.insert(0, str(kb_path))

from ..client import LLMClient
from .. import Message, MessageRole, Config

from .models import (
    PaperMetadata,
    ThesisSection,
    ThesisOutline,
    FormattingRules,
    CitationStyle,
    ThesisConfig,
)
from .prompts import (
    THESIS_WRITER_SYSTEM_PROMPT,
    OUTLINE_GENERATION_PROMPT,
    SECTION_WRITING_PROMPT,
    PAPER_SUMMARY_PROMPT,
    SECTION_REFINEMENT_PROMPT,
)
from .paper_fetcher import PaperFetcher
from .citation_manager import CitationManager
from .docx_generator import FormattingInterpreter, ThesisDocxGenerator, create_thesis_document

try:
    from notebook.storage import get_store
    from notebook.models import PaperCreate
    KNOWLEDGE_BASE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_BASE_AVAILABLE = False

logger = logging.getLogger(__name__)


class ThesisAgent:
    """Agent for academic thesis writing with RAG."""
    
    def __init__(
        self,
        config: Optional[ThesisConfig] = None,
        citation_style: CitationStyle = CitationStyle.GB_T_7714
    ):
        """Initialize thesis agent.
        
        Args:
            config: Thesis configuration
            citation_style: Citation style to use
        """
        self.config = config
        self.llm = LLMClient()
        self.conversation: List[Message] = []
        
        # Initialize components
        self.paper_fetcher = PaperFetcher()
        self.citation_manager = CitationManager(style=citation_style)
        
        # Knowledge base
        self.kb_store = None
        if KNOWLEDGE_BASE_AVAILABLE:
            try:
                self.kb_store = get_store()
                self.kb_store.ensure_collection()
                logger.info("Knowledge base initialized successfully")
            except Exception as e:
                logger.debug(f"Knowledge base not available: {e}")
        else:
            logger.debug("Knowledge base module not found (optional feature)")
        
        # Set system prompt
        self.conversation.append(
            Message(role=MessageRole.SYSTEM, content=THESIS_WRITER_SYSTEM_PROMPT)
        )
        
        # Sections storage
        self.sections: Dict[str, ThesisSection] = {}
        self.outline: Optional[ThesisOutline] = None
    
    def search_papers(
        self,
        query: str,
        sources: List[str] = ["arxiv", "semantic_scholar"],
        limit: int = 10,
        auto_add: bool = True
    ) -> List[PaperMetadata]:
        """Search for academic papers.
        
        Args:
            query: Search query (supports Chinese and English)
            sources: Sources to search
            limit: Maximum papers per source
            auto_add: Automatically add papers to knowledge base
            
        Returns:
            List of papers found
        """
        logger.info(f"Searching papers: {query}")
        papers = self.paper_fetcher.search_papers(query, sources, limit)
        
        if auto_add and papers:
            self.add_papers_to_kb(papers)
        
        return papers
    
    def add_papers_to_kb(self, papers: List[PaperMetadata]) -> int:
        """Add papers to knowledge base.
        
        Args:
            papers: Papers to add
            
        Returns:
            Number of papers added
        """
        if not self.kb_store:
            logger.debug("Knowledge base not available, skipping paper storage")
            return 0
        
        added = 0
        for paper in papers:
            try:
                # Create paper note
                note_id = f"paper_{paper.arxiv_id or paper.doi or paper.title[:50]}"
                
                # Prepare content
                content_parts = []
                content_parts.append(f"# {paper.title}\n")
                content_parts.append(f"**Authors:** {', '.join(paper.authors)}\n")
                content_parts.append(f"**Year:** {paper.publication_year}\n")
                if paper.publication_venue:
                    content_parts.append(f"**Venue:** {paper.publication_venue}\n")
                if paper.citation_count:
                    content_parts.append(f"**Citations:** {paper.citation_count}\n")
                content_parts.append(f"\n## Abstract\n{paper.abstract}\n")
                
                content = "\n".join(content_parts)
                
                # Prepare tags
                tags = ["thesis", "paper", "research"] + paper.tags
                
                # Create paper metadata as dict for payload
                metadata = {
                    "note_id": note_id,
                    "title": paper.title,
                    "title_cn": paper.title_cn,
                    "title_en": paper.title_en,
                    "authors": paper.authors,
                    "authors_cn": paper.authors_cn,
                    "authors_en": paper.authors_en,
                    "doi": paper.doi,
                    "arxiv_id": paper.arxiv_id,
                    "semantic_scholar_id": paper.semantic_scholar_id,
                    "publication_year": paper.publication_year,
                    "publication_venue": paper.publication_venue,
                    "citation_count": paper.citation_count,
                    "source_url": paper.source_url,
                    "pdf_url": paper.pdf_url,
                    "language": paper.language,
                    "keywords": paper.keywords,
                    "tldr": paper.tldr,
                }
                
                # Store in knowledge base
                self.kb_store.upsert_note_version(
                    note_id=note_id,
                    title=paper.title,
                    content=content,
                    tags=tags,
                    status="verified",
                    metadata=metadata
                )
                
                added += 1
                logger.info(f"Added paper to KB: {paper.title}")
                
            except Exception as e:
                logger.error(f"Failed to add paper {paper.title}: {e}")
                continue
        
        return added
    
    def generate_outline(
        self,
        topic: str,
        requirements: Optional[str] = None
    ) -> ThesisOutline:
        """Generate thesis outline.
        
        Args:
            topic: Research topic
            requirements: Additional requirements
            
        Returns:
            Thesis outline
        """
        prompt = OUTLINE_GENERATION_PROMPT.format(topic=topic)
        if requirements:
            prompt += f"\n\n额外要求：\n{requirements}"
        
        response = self.llm.simple_query(prompt, temperature=0.7)
        
        # Extract JSON
        json_str = self._extract_json(response)
        outline_dict = json.loads(json_str)
        
        # Create outline object
        outline = ThesisOutline(
            title=outline_dict.get("title", topic),
            chapters=outline_dict.get("chapters", []),
            total_chapters=len(outline_dict.get("chapters", [])),
            requirements=requirements
        )
        
        self.outline = outline
        return outline
    
    def write_section(
        self,
        section_id: str,
        section_title: str,
        target_words: int = 800,
        user_requirements: Optional[str] = None,
        use_rag: bool = True
    ) -> ThesisSection:
        """Write a thesis section with RAG.
        
        Args:
            section_id: Section ID (e.g., "1.1")
            section_title: Section title
            target_words: Target word count
            user_requirements: Additional requirements
            use_rag: Whether to use knowledge base for RAG
            
        Returns:
            Generated section
        """
        logger.info(f"Writing section: {section_id} {section_title}")
        
        # Get outline context
        outline_context = ""
        if self.outline:
            outline_context = json.dumps(self.outline.chapters, ensure_ascii=False, indent=2)
        
        # Get paper context from knowledge base
        paper_context = ""
        if use_rag and self.kb_store:
            # Search for relevant papers
            search_query = f"{section_title} {user_requirements or ''}"
            papers = self.kb_store.search(search_query, limit=5, tags=["paper", "thesis"])
            
            if papers:
                context_parts = []
                for i, paper in enumerate(papers, 1):
                    title = paper.get("title", "Unknown")
                    content = paper.get("content", "")[:500]  # First 500 chars
                    score = paper.get("score", 0)
                    context_parts.append(f"[文献{i}] {title}\n相关度: {score:.3f}\n{content}...")
                
                paper_context = "\n\n".join(context_parts)
        
        # Generate section content
        prompt = SECTION_WRITING_PROMPT.format(
            section_id=section_id,
            section_title=section_title,
            outline_context=outline_context or "无",
            user_requirements=user_requirements or "无",
            paper_context=paper_context or "无相关文献",
            target_words=target_words
        )
        
        response = self.llm.simple_query(prompt, temperature=0.7, max_tokens=2000)
        
        # Parse citations from content
        citation_keys = self.citation_manager.parse_citations_from_text(response)
        
        # Create section
        section = ThesisSection(
            section_id=section_id,
            title=section_title,
            content=response,
            citations=citation_keys,
            word_count=len(response),
            generated_at=datetime.now().isoformat(),
            outline_context=outline_context,
            requirements=user_requirements
        )
        
        # Store section
        self.sections[section_id] = section
        
        return section
    
    def refine_section(
        self,
        section_id: str,
        feedback: str
    ) -> ThesisSection:
        """Refine an existing section based on feedback.
        
        Args:
            section_id: Section ID to refine
            feedback: User feedback
            
        Returns:
            Refined section
        """
        if section_id not in self.sections:
            raise ValueError(f"Section {section_id} not found")
        
        section = self.sections[section_id]
        
        prompt = SECTION_REFINEMENT_PROMPT.format(
            original_content=section.content,
            user_feedback=feedback
        )
        
        response = self.llm.simple_query(prompt, temperature=0.7, max_tokens=2000)
        
        # Update section
        section.content = response
        section.word_count = len(response)
        section.citations = self.citation_manager.parse_citations_from_text(response)
        
        return section
    
    def export_docx(
        self,
        output_path: str,
        formatting_spec: str = "标准中国高校硕士学位论文",
        include_cover: bool = True,
        **metadata
    ) -> str:
        """Export thesis to .docx file.
        
        Args:
            output_path: Output file path
            formatting_spec: Natural language formatting specification
            include_cover: Include cover page
            **metadata: Additional metadata (author, institution, etc.)
            
        Returns:
            Path to generated file
        """
        # Get sections in order
        section_ids = sorted(self.sections.keys())
        sections = [self.sections[sid] for sid in section_ids]
        
        # Generate bibliography
        references = self.citation_manager.generate_bibliography()
        
        # Get metadata
        title = metadata.get("title", self.outline.title if self.outline else "论文")
        author = metadata.get("author", "作者")
        
        # Create document
        output_path = create_thesis_document(
            sections=sections,
            references=references,
            formatting_spec=formatting_spec,
            title=title,
            author=author,
            output_path=output_path,
            **metadata
        )
        
        return output_path
    
    def save_section(self, section_id: str, output_path: str):
        """Save a section to markdown file.
        
        Args:
            section_id: Section ID
            output_path: Output file path
        """
        if section_id not in self.sections:
            raise ValueError(f"Section {section_id} not found")
        
        section = self.sections[section_id]
        
        content = f"# {section.section_id} {section.title}\n\n"
        content += section.content
        
        Path(output_path).write_text(content, encoding="utf-8")
        logger.info(f"Section saved to {output_path}")
    
    def load_section(self, section_id: str, filepath: str):
        """Load a section from markdown file.
        
        Args:
            section_id: Section ID
            filepath: File path to load from
        """
        content = Path(filepath).read_text(encoding="utf-8")
        
        # Extract title from first heading
        lines = content.split('\n')
        title = section_id
        for line in lines:
            if line.startswith('# '):
                title = line[2:].strip()
                # Remove section_id if present
                if title.startswith(section_id):
                    title = title[len(section_id):].strip()
                break
        
        # Remove first heading from content
        content = '\n'.join(lines[1:]).strip()
        
        section = ThesisSection(
            section_id=section_id,
            title=title,
            content=content,
            word_count=len(content)
        )
        
        self.sections[section_id] = section
    
    def list_papers(self, tags: Optional[List[str]] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """List papers in knowledge base.
        
        Args:
            tags: Filter by tags
            limit: Maximum results
            
        Returns:
            List of papers
        """
        if not self.kb_store:
            return []
        
        # Search with empty query to get all papers
        filter_tags = tags or ["paper"]
        papers = self.kb_store.search("", limit=limit, tags=filter_tags)
        
        return papers
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text.
        
        Args:
            text: Text containing JSON
            
        Returns:
            JSON string
        """
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1:
            return text[start:end+1]
        
        return text
