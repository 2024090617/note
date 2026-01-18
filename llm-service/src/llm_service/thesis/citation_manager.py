"""Citation management and formatting."""

from typing import List, Optional, Dict, Any
import re
from datetime import datetime

from .models import PaperMetadata, CitationStyle


class CitationManager:
    """Manage citations and generate bibliographies."""
    
    def __init__(self, style: CitationStyle = CitationStyle.GB_T_7714):
        """Initialize citation manager.
        
        Args:
            style: Citation style to use
        """
        self.style = style
        self.papers: Dict[str, PaperMetadata] = {}  # citation_key -> paper
        self.citation_counter = 0
    
    def add_paper(self, paper: PaperMetadata) -> str:
        """Add a paper and get its citation key.
        
        Args:
            paper: Paper metadata
            
        Returns:
            Citation key (e.g., "[1]", "[2]")
        """
        # Check if paper already added (by DOI or ArXiv ID)
        existing_key = self._find_existing_paper(paper)
        if existing_key:
            return existing_key
        
        # Assign new citation number
        self.citation_counter += 1
        citation_key = str(self.citation_counter)
        self.papers[citation_key] = paper
        
        return citation_key
    
    def format_inline_citation(self, citation_keys: List[str]) -> str:
        """Format inline citation.
        
        Args:
            citation_keys: List of citation keys
            
        Returns:
            Formatted inline citation (e.g., "[1,2,3]" or "[1-3]")
        """
        if not citation_keys:
            return ""
        
        # Convert to integers and sort
        nums = sorted([int(k) for k in citation_keys])
        
        # Group consecutive numbers
        groups = []
        start = nums[0]
        end = nums[0]
        
        for i in range(1, len(nums)):
            if nums[i] == end + 1:
                end = nums[i]
            else:
                if start == end:
                    groups.append(str(start))
                elif end == start + 1:
                    groups.append(f"{start},{end}")
                else:
                    groups.append(f"{start}-{end}")
                start = end = nums[i]
        
        # Add last group
        if start == end:
            groups.append(str(start))
        elif end == start + 1:
            groups.append(f"{start},{end}")
        else:
            groups.append(f"{start}-{end}")
        
        return "[" + ",".join(groups) + "]"
    
    def generate_bibliography(self) -> List[str]:
        """Generate complete bibliography.
        
        Returns:
            List of formatted reference entries
        """
        entries = []
        
        # Sort by citation number
        sorted_keys = sorted(self.papers.keys(), key=lambda k: int(k))
        
        for key in sorted_keys:
            paper = self.papers[key]
            entry = self._format_reference(key, paper)
            entries.append(entry)
        
        return entries
    
    def _format_reference(self, citation_key: str, paper: PaperMetadata) -> str:
        """Format a single reference entry.
        
        Args:
            citation_key: Citation number
            paper: Paper metadata
            
        Returns:
            Formatted reference string
        """
        if self.style == CitationStyle.GB_T_7714:
            return self._format_gbt7714(citation_key, paper)
        elif self.style == CitationStyle.APA:
            return self._format_apa(citation_key, paper)
        elif self.style == CitationStyle.IEEE:
            return self._format_ieee(citation_key, paper)
        else:
            return self._format_gbt7714(citation_key, paper)  # Default
    
    def _format_gbt7714(self, citation_key: str, paper: PaperMetadata) -> str:
        """Format citation in GB/T 7714-2015 style.
        
        Format: [序号] 主要责任者. 文献题名[文献类型标志]. 出版地: 出版者, 出版年: 起止页码.
        
        Args:
            citation_key: Citation number
            paper: Paper metadata
            
        Returns:
            Formatted reference
        """
        parts = [f"[{citation_key}]"]
        
        # Authors (up to 3, then et al)
        if paper.authors:
            authors = paper.authors[:3]
            author_str = ", ".join(authors)
            if len(paper.authors) > 3:
                author_str += ", et al"
            parts.append(author_str + ".")
        
        # Title
        title = paper.title_en or paper.title
        parts.append(title)
        
        # Document type
        if paper.arxiv_id:
            doc_type = "[J/OL]"  # Online journal/preprint
        elif paper.publication_venue:
            if "conference" in paper.publication_venue.lower() or "proceedings" in paper.publication_venue.lower():
                doc_type = "[C]"  # Conference
            else:
                doc_type = "[J]"  # Journal
        else:
            doc_type = "[J]"
        parts.append(doc_type + ".")
        
        # Venue and year
        venue_parts = []
        if paper.publication_venue:
            venue_parts.append(paper.publication_venue)
        
        if paper.publication_year:
            venue_parts.append(str(paper.publication_year))
        
        if paper.volume:
            volume_str = f"{paper.volume}"
            if paper.issue:
                volume_str += f"({paper.issue})"
            venue_parts.append(volume_str)
        
        if paper.pages:
            venue_parts.append(paper.pages)
        
        if venue_parts:
            parts.append(", ".join(venue_parts) + ".")
        
        # DOI or URL
        if paper.doi:
            parts.append(f"DOI: {paper.doi}.")
        elif paper.source_url:
            parts.append(f"Available: {paper.source_url}.")
        
        return " ".join(parts)
    
    def _format_apa(self, citation_key: str, paper: PaperMetadata) -> str:
        """Format citation in APA style.
        
        Args:
            citation_key: Citation number
            paper: Paper metadata
            
        Returns:
            Formatted reference
        """
        parts = [f"[{citation_key}]"]
        
        # Authors (Last, F. M.)
        if paper.authors:
            author_list = []
            for author in paper.authors[:7]:  # APA: list up to 7 authors
                name_parts = author.split()
                if len(name_parts) >= 2:
                    last_name = name_parts[-1]
                    initials = ". ".join([n[0] for n in name_parts[:-1]]) + "."
                    author_list.append(f"{last_name}, {initials}")
                else:
                    author_list.append(author)
            
            if len(paper.authors) > 7:
                author_str = ", ".join(author_list) + ", et al."
            else:
                author_str = ", ".join(author_list)
            parts.append(author_str)
        
        # Year
        if paper.publication_year:
            parts.append(f"({paper.publication_year}).")
        
        # Title
        title = paper.title_en or paper.title
        parts.append(f"{title}.")
        
        # Venue
        if paper.publication_venue:
            venue_str = f"*{paper.publication_venue}*"
            if paper.volume:
                venue_str += f", {paper.volume}"
                if paper.issue:
                    venue_str += f"({paper.issue})"
            if paper.pages:
                venue_str += f", {paper.pages}"
            parts.append(venue_str + ".")
        
        # DOI or URL
        if paper.doi:
            parts.append(f"https://doi.org/{paper.doi}")
        elif paper.source_url:
            parts.append(paper.source_url)
        
        return " ".join(parts)
    
    def _format_ieee(self, citation_key: str, paper: PaperMetadata) -> str:
        """Format citation in IEEE style.
        
        Args:
            citation_key: Citation number
            paper: Paper metadata
            
        Returns:
            Formatted reference
        """
        parts = [f"[{citation_key}]"]
        
        # Authors (F. M. Last)
        if paper.authors:
            author_list = []
            for author in paper.authors:
                name_parts = author.split()
                if len(name_parts) >= 2:
                    initials = ". ".join([n[0] for n in name_parts[:-1]]) + "."
                    last_name = name_parts[-1]
                    author_list.append(f"{initials} {last_name}")
                else:
                    author_list.append(author)
            
            if len(author_list) <= 6:
                author_str = ", ".join(author_list)
            else:
                author_str = ", ".join(author_list[:1]) + " et al."
            parts.append(author_str + ",")
        
        # Title
        title = paper.title_en or paper.title
        parts.append(f'"{title},"')
        
        # Venue
        if paper.publication_venue:
            venue_str = f"*{paper.publication_venue}*"
            if paper.volume:
                venue_str += f", vol. {paper.volume}"
            if paper.issue:
                venue_str += f", no. {paper.issue}"
            if paper.pages:
                venue_str += f", pp. {paper.pages}"
            parts.append(venue_str + ",")
        
        # Year
        if paper.publication_year:
            parts.append(f"{paper.publication_year}.")
        
        # DOI
        if paper.doi:
            parts.append(f"doi: {paper.doi}")
        
        return " ".join(parts)
    
    def _find_existing_paper(self, paper: PaperMetadata) -> Optional[str]:
        """Check if paper already exists in citations.
        
        Args:
            paper: Paper to check
            
        Returns:
            Existing citation key or None
        """
        for key, existing_paper in self.papers.items():
            # Match by DOI
            if paper.doi and existing_paper.doi and paper.doi == existing_paper.doi:
                return key
            
            # Match by ArXiv ID
            if paper.arxiv_id and existing_paper.arxiv_id and paper.arxiv_id == existing_paper.arxiv_id:
                return key
            
            # Match by title (fuzzy)
            if paper.title.lower().strip() == existing_paper.title.lower().strip():
                return key
        
        return None
    
    def parse_citations_from_text(self, text: str) -> List[str]:
        """Extract citation keys from text.
        
        Args:
            text: Text containing citations like [1], [2,3], [4-6]
            
        Returns:
            List of citation keys
        """
        citation_keys = set()
        
        # Pattern: [1], [2,3], [4-6]
        pattern = r'\[(\d+(?:[-,]\d+)*)\]'
        matches = re.findall(pattern, text)
        
        for match in matches:
            # Split by comma
            for part in match.split(','):
                # Check for range
                if '-' in part:
                    start, end = part.split('-')
                    citation_keys.update(str(i) for i in range(int(start), int(end) + 1))
                else:
                    citation_keys.add(part)
        
        return sorted(citation_keys, key=int)
    
    def export_bibtex(self) -> str:
        """Export all papers as BibTeX.
        
        Returns:
            BibTeX string
        """
        entries = []
        
        for key, paper in self.papers.items():
            if paper.bibtex:
                entries.append(paper.bibtex)
            else:
                # Generate basic BibTeX entry
                entry = self._generate_bibtex_entry(key, paper)
                entries.append(entry)
        
        return "\n\n".join(entries)
    
    def _generate_bibtex_entry(self, citation_key: str, paper: PaperMetadata) -> str:
        """Generate BibTeX entry for a paper.
        
        Args:
            citation_key: Citation key
            paper: Paper metadata
            
        Returns:
            BibTeX entry
        """
        # Determine entry type
        if paper.arxiv_id:
            entry_type = "article"
        elif "conference" in (paper.publication_venue or "").lower():
            entry_type = "inproceedings"
        else:
            entry_type = "article"
        
        # Create citation key
        if paper.authors:
            first_author_last = paper.authors[0].split()[-1]
        else:
            first_author_last = "Unknown"
        
        bibtex_key = f"{first_author_last}{paper.publication_year}"
        
        lines = [f"@{entry_type}{{{bibtex_key},"]
        
        # Title
        lines.append(f'  title = {{{paper.title}}},')
        
        # Authors
        if paper.authors:
            authors_str = " and ".join(paper.authors)
            lines.append(f'  author = {{{authors_str}}},')
        
        # Year
        lines.append(f'  year = {{{paper.publication_year}}},')
        
        # Venue
        if paper.publication_venue:
            if entry_type == "inproceedings":
                lines.append(f'  booktitle = {{{paper.publication_venue}}},')
            else:
                lines.append(f'  journal = {{{paper.publication_venue}}},')
        
        # Volume/Issue/Pages
        if paper.volume:
            lines.append(f'  volume = {{{paper.volume}}},')
        if paper.issue:
            lines.append(f'  number = {{{paper.issue}}},')
        if paper.pages:
            lines.append(f'  pages = {{{paper.pages}}},')
        
        # DOI
        if paper.doi:
            lines.append(f'  doi = {{{paper.doi}}},')
        
        # ArXiv
        if paper.arxiv_id:
            lines.append(f'  eprint = {{{paper.arxiv_id}}},')
            lines.append(f'  archivePrefix = {{arXiv}},')
        
        # URL
        if paper.source_url:
            lines.append(f'  url = {{{paper.source_url}}},')
        
        lines.append("}")
        
        return "\n".join(lines)
