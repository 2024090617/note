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

# Skillkit for Anthropic Agent Skills
try:
    from skillkit import SkillManager
    SKILLKIT_AVAILABLE = True
except ImportError:
    SKILLKIT_AVAILABLE = False

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
        
        # Initialize skillkit for enhanced capabilities
        self.skill_manager = None
        self._skill_cache: Dict[str, str] = {}
        if SKILLKIT_AVAILABLE:
            try:
                # Skills directory relative to llm-service root
                skills_path = Path(__file__).parent.parent.parent.parent / ".claude" / "skills"
                if skills_path.exists():
                    # Use anthropic_config_dir for .claude/skills path
                    self.skill_manager = SkillManager(
                        anthropic_config_dir=str(skills_path.parent),  # .claude directory
                        project_skill_dir=""  # Disable project skills
                    )
                    self.skill_manager.discover()
                    available_skills = [s.name for s in self.skill_manager.list_skills()]
                    logger.info(f"Skillkit initialized with skills: {available_skills}")
                else:
                    logger.debug(f"Skills directory not found: {skills_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize skillkit: {e}")
        else:
            logger.debug("Skillkit not available (optional feature)")
    
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
    
    def _get_skill_context(self, skill_name: str, arguments: str = "") -> Optional[str]:
        """Get skill instructions for prompt injection.
        
        Args:
            skill_name: Name of the skill to load (e.g., 'doc-coauthoring', 'docx', 'pdf')
            arguments: Optional arguments to pass to the skill
            
        Returns:
            Skill instructions as string, or None if not available
        """
        if not self.skill_manager:
            return None
        
        # Check cache first
        cache_key = f"{skill_name}:{arguments}"
        if cache_key in self._skill_cache:
            return self._skill_cache[cache_key]
        
        try:
            # Invoke skill to get its full content
            result = self.skill_manager.invoke_skill(skill_name, arguments)
            if result:
                self._skill_cache[cache_key] = result
                logger.debug(f"Loaded skill context: {skill_name}")
                return result
        except Exception as e:
            logger.warning(f"Failed to load skill {skill_name}: {e}")
        
        return None
    
    def list_available_skills(self) -> List[Dict[str, str]]:
        """List all available skills from skillkit.
        
        Returns:
            List of skill info dicts with name and description
        """
        if not self.skill_manager:
            return []
        
        skills = []
        for skill in self.skill_manager.list_skills():
            skills.append({
                "name": skill.name,
                "description": skill.description
            })
        return skills
    
    def write_section_with_skill(
        self,
        section_id: str,
        section_title: str,
        target_words: int = 800,
        user_requirements: Optional[str] = None,
        use_rag: bool = True,
        use_coauthoring_skill: bool = True
    ) -> ThesisSection:
        """Write a thesis section using doc-coauthoring skill workflow.
        
        This enhanced method uses the doc-coauthoring skill for a structured
        3-stage writing process: Context Gathering → Refinement → Reader Testing.
        
        Args:
            section_id: Section ID (e.g., "1.1")
            section_title: Section title
            target_words: Target word count
            user_requirements: Additional requirements
            use_rag: Whether to use knowledge base for RAG
            use_coauthoring_skill: Whether to use doc-coauthoring skill
            
        Returns:
            Generated section
        """
        logger.info(f"Writing section with skill: {section_id} {section_title}")
        
        # Get skill context for enhanced writing workflow
        skill_context = ""
        if use_coauthoring_skill:
            coauthoring_skill = self._get_skill_context("doc-coauthoring")
            if coauthoring_skill:
                skill_context = f"""
## Writing Workflow (from doc-coauthoring skill)

Follow this structured approach for high-quality academic writing:

{coauthoring_skill[:2000]}  # Truncate to fit context

---
"""
        
        # Get outline context
        outline_context = ""
        if self.outline:
            outline_context = json.dumps(self.outline.chapters, ensure_ascii=False, indent=2)
        
        # Get paper context from knowledge base
        paper_context = ""
        if use_rag and self.kb_store:
            search_query = f"{section_title} {user_requirements or ''}"
            papers = self.kb_store.search(search_query, limit=5, tags=["paper", "thesis"])
            
            if papers:
                context_parts = []
                for i, paper in enumerate(papers, 1):
                    title = paper.get("title", "Unknown")
                    content = paper.get("content", "")[:500]
                    score = paper.get("score", 0)
                    context_parts.append(f"[文献{i}] {title}\n相关度: {score:.3f}\n{content}...")
                
                paper_context = "\n\n".join(context_parts)
        
        # Enhanced prompt with skill context
        enhanced_prompt = f"""{skill_context}
## Section Writing Task

请为以下章节撰写学术论文内容:

**章节编号**: {section_id}
**章节标题**: {section_title}
**目标字数**: {target_words}字

**论文大纲上下文**:
{outline_context or "无"}

**用户要求**:
{user_requirements or "无"}

**相关文献**:
{paper_context or "无相关文献"}

请按照学术写作规范，撰写结构清晰、论证严谨的内容。如有引用文献，请使用[作者, 年份]格式标注。
"""
        
        response = self.llm.simple_query(enhanced_prompt, temperature=0.7, max_tokens=2000)
        
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
    
    def export_docx_with_skill(
        self,
        output_path: str,
        formatting_spec: str = "标准中国高校硕士学位论文",
        include_cover: bool = True,
        use_docx_skill: bool = True,
        **metadata
    ) -> str:
        """Export thesis to .docx file with enhanced formatting using docx skill.
        
        This method uses the docx skill for advanced OOXML features like
        tracked changes, comments, and professional formatting.
        
        Args:
            output_path: Output file path
            formatting_spec: Natural language formatting specification
            include_cover: Include cover page
            use_docx_skill: Whether to use docx skill for enhanced formatting
            **metadata: Additional metadata (author, institution, etc.)
            
        Returns:
            Path to generated file
        """
        # Get skill context for enhanced document generation
        skill_guidance = ""
        if use_docx_skill:
            docx_skill = self._get_skill_context("docx")
            if docx_skill:
                skill_guidance = docx_skill[:1500]  # Truncate for context
                logger.info("Using docx skill for enhanced document formatting")
        
        # Get sections in order
        section_ids = sorted(self.sections.keys())
        sections = [self.sections[sid] for sid in section_ids]
        
        # Generate bibliography
        references = self.citation_manager.generate_bibliography()
        
        # Get metadata (pop to avoid duplicate keyword args)
        title = metadata.pop("title", self.outline.title if self.outline else "论文")
        author = metadata.pop("author", "作者")
        
        # If skill guidance available, enhance the formatting spec
        if skill_guidance:
            # Add skill-enhanced formatting hints to metadata
            metadata["_docx_skill_guidance"] = skill_guidance
        
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
    
    def export_pdf(
        self,
        output_path: str,
        formatting_spec: str = "标准中国高校硕士学位论文",
        **metadata
    ) -> str:
        """Export thesis to PDF file using pdf skill.
        
        This method first exports to .docx then converts to PDF,
        using the pdf skill for enhanced PDF handling.
        
        Args:
            output_path: Output file path (should end with .pdf)
            formatting_spec: Natural language formatting specification
            **metadata: Additional metadata
            
        Returns:
            Path to generated PDF file
        """
        import subprocess
        import tempfile
        
        # Get PDF skill context
        pdf_skill = self._get_skill_context("pdf")
        if pdf_skill:
            logger.info("Using pdf skill for enhanced PDF generation")
        
        # First export to docx
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            docx_path = tmp.name
        
        self.export_docx_with_skill(
            output_path=docx_path,
            formatting_spec=formatting_spec,
            **metadata
        )
        
        # Convert to PDF using pandoc or libreoffice
        try:
            # Try pandoc first
            result = subprocess.run(
                ["pandoc", docx_path, "-o", output_path],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                logger.info(f"PDF exported via pandoc: {output_path}")
                return output_path
        except FileNotFoundError:
            pass
        
        try:
            # Fallback to libreoffice
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf", 
                 "--outdir", str(Path(output_path).parent), docx_path],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # LibreOffice names the file based on input
                generated_pdf = Path(docx_path).with_suffix(".pdf")
                if generated_pdf.exists():
                    generated_pdf.rename(output_path)
                logger.info(f"PDF exported via libreoffice: {output_path}")
                return output_path
        except FileNotFoundError:
            pass
        
        raise RuntimeError(
            "PDF conversion failed. Please install pandoc or libreoffice.\n"
            "  - macOS: brew install pandoc\n"
            "  - Ubuntu: apt install pandoc\n"
            "  - Or install LibreOffice"
        )
    
    def interactive_write_section(
        self,
        section_id: str,
        section_title: str,
        target_words: int = 800
    ) -> ThesisSection:
        """Interactive section writing using full doc-coauthoring workflow.
        
        This method implements the complete 3-stage doc-coauthoring workflow:
        1. Context Gathering - Gather all relevant information
        2. Refinement & Structure - Iteratively build the section
        3. Reader Testing - Verify the section works for readers
        
        Args:
            section_id: Section ID
            section_title: Section title
            target_words: Target word count
            
        Returns:
            Final generated section
        """
        coauthoring_skill = self._get_skill_context("doc-coauthoring")
        
        # Stage 1: Context Gathering
        stage1_prompt = f"""
{coauthoring_skill[:1500] if coauthoring_skill else ""}

## Stage 1: Context Gathering for Academic Section

我们正在为学位论文撰写以下章节:
- 章节编号: {section_id}
- 章节标题: {section_title}
- 目标字数: {target_words}

请先分析这个章节需要的核心内容和结构，列出：
1. 这个章节应该包含哪些关键论点？
2. 需要哪些背景知识或理论基础？
3. 应该引用哪些类型的文献？
4. 有哪些潜在的写作难点？

请以结构化的方式输出分析结果。
"""
        
        context_analysis = self.llm.simple_query(stage1_prompt, temperature=0.5)
        logger.info(f"Stage 1 complete: Context gathered for {section_id}")
        
        # Stage 2: Writing with RAG
        section = self.write_section_with_skill(
            section_id=section_id,
            section_title=section_title,
            target_words=target_words,
            user_requirements=context_analysis,
            use_rag=True,
            use_coauthoring_skill=True
        )
        
        # Stage 3: Reader Testing / Self-Review
        stage3_prompt = f"""
## Stage 3: Reader Testing / Self-Review

请以一个"没有上下文的新读者"的视角审阅以下学术内容:

{section.content}

请检查:
1. 内容是否清晰易懂？
2. 逻辑是否连贯？
3. 是否有未解释的术语或概念？
4. 论证是否充分？
5. 引用是否恰当？

如果发现问题，请指出具体位置和改进建议。
"""
        
        review_feedback = self.llm.simple_query(stage3_prompt, temperature=0.3)
        
        # If significant issues found, refine the section
        if any(word in review_feedback.lower() for word in ["问题", "建议", "改进", "不清晰", "缺少"]):
            logger.info(f"Stage 3: Issues found, refining section {section_id}")
            section = self.refine_section(section_id, review_feedback)
        
        logger.info(f"Interactive writing complete for section {section_id}")
        return section
