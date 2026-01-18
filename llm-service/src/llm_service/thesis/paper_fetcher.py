"""Paper fetching from academic databases."""

from typing import List, Optional, Dict, Any
import requests
from datetime import datetime
import logging
import time

from .models import PaperMetadata

logger = logging.getLogger(__name__)


class PaperFetcher:
    """Fetch papers from multiple academic sources."""
    
    def __init__(self):
        """Initialize paper fetcher."""
        self.arxiv_base = "http://export.arxiv.org/api/query"
        self.semantic_scholar_base = "https://api.semanticscholar.org/graph/v1"
        
    def search_papers(
        self,
        query: str,
        sources: List[str] = ["arxiv", "semantic_scholar"],
        limit: int = 10
    ) -> List[PaperMetadata]:
        """Search papers from multiple sources.
        
        Args:
            query: Search query (supports Chinese and English)
            sources: List of sources to search ("arxiv", "semantic_scholar")
            limit: Maximum number of papers per source
            
        Returns:
            List of paper metadata
        """
        papers = []
        
        if "arxiv" in sources:
            try:
                arxiv_papers = self.search_arxiv(query, limit)
                papers.extend(arxiv_papers)
                logger.info(f"Found {len(arxiv_papers)} papers from ArXiv")
            except Exception as e:
                logger.error(f"ArXiv search failed: {e}")
        
        if "semantic_scholar" in sources:
            try:
                ss_papers = self.search_semantic_scholar(query, limit)
                papers.extend(ss_papers)
                logger.info(f"Found {len(ss_papers)} papers from Semantic Scholar")
            except Exception as e:
                logger.error(f"Semantic Scholar search failed: {e}")
        
        # Remove duplicates based on DOI or ArXiv ID
        papers = self._deduplicate_papers(papers)
        
        return papers
    
    def search_arxiv(self, query: str, max_results: int = 10) -> List[PaperMetadata]:
        """Search ArXiv for papers.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of paper metadata
        """
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }
        
        response = requests.get(self.arxiv_base, params=params)
        response.raise_for_status()
        
        papers = self._parse_arxiv_response(response.text)
        return papers
    
    def search_semantic_scholar(self, query: str, limit: int = 10, max_retries: int = 2) -> List[PaperMetadata]:
        """Search Semantic Scholar for papers.
        
        Args:
            query: Search query
            limit: Maximum number of results
            max_retries: Maximum retry attempts on rate limit
            
        Returns:
            List of paper metadata
        """
        url = f"{self.semantic_scholar_base}/paper/search"
        params = {
            "query": query,
            "limit": limit,
            "fields": "title,authors,year,abstract,citationCount,venue,externalIds,url,openAccessPdf"
        }
        
        headers = {
            "User-Agent": "ThesisAgent/1.0 (mailto:your-email@example.com)"
        }
        
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                papers = self._parse_semantic_scholar_response(data)
                
                return papers
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:  # Rate limit
                    if attempt < max_retries:
                        wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries} retries. Try again later or use --sources arxiv")
                        raise
                else:
                    raise
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries + 1})")
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                raise
        
        return []
    
    def get_paper_by_arxiv_id(self, arxiv_id: str) -> Optional[PaperMetadata]:
        """Get paper metadata by ArXiv ID.
        
        Args:
            arxiv_id: ArXiv ID (e.g., "2301.12345")
            
        Returns:
            Paper metadata or None if not found
        """
        params = {
            "id_list": arxiv_id,
            "max_results": 1
        }
        
        response = requests.get(self.arxiv_base, params=params)
        response.raise_for_status()
        
        papers = self._parse_arxiv_response(response.text)
        return papers[0] if papers else None
    
    def get_paper_by_doi(self, doi: str) -> Optional[PaperMetadata]:
        """Get paper metadata by DOI using Semantic Scholar.
        
        Args:
            doi: DOI identifier
            
        Returns:
            Paper metadata or None if not found
        """
        url = f"{self.semantic_scholar_base}/paper/DOI:{doi}"
        params = {
            "fields": "title,authors,year,abstract,citationCount,venue,externalIds,url,openAccessPdf"
        }
        
        headers = {
            "User-Agent": "ThesisAgent/1.0 (mailto:your-email@example.com)"
        }
        
        try:
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            paper = self._parse_semantic_scholar_paper(data)
            
            return paper
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    def _parse_arxiv_response(self, xml_text: str) -> List[PaperMetadata]:
        """Parse ArXiv XML response.
        
        Args:
            xml_text: XML response text
            
        Returns:
            List of paper metadata
        """
        import xml.etree.ElementTree as ET
        
        papers = []
        root = ET.fromstring(xml_text)
        
        # ArXiv uses Atom namespace
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        for entry in root.findall("atom:entry", ns):
            try:
                title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ns).text.strip().replace("\n", " ")
                
                # Extract ArXiv ID from the id field
                id_text = entry.find("atom:id", ns).text
                arxiv_id = id_text.split("/abs/")[-1]
                
                # Authors
                authors = [
                    author.find("atom:name", ns).text
                    for author in entry.findall("atom:author", ns)
                ]
                
                # Publication date
                published = entry.find("atom:published", ns).text
                year = int(published.split("-")[0])
                
                # PDF URL
                pdf_link = None
                for link in entry.findall("atom:link", ns):
                    if link.get("title") == "pdf":
                        pdf_link = link.get("href")
                        break
                
                paper = PaperMetadata(
                    title=title,
                    title_en=title,
                    authors=authors,
                    authors_en=authors,
                    abstract=summary,
                    abstract_en=summary,
                    arxiv_id=arxiv_id,
                    publication_year=year,
                    publication_venue="arXiv",
                    pdf_url=pdf_link,
                    source_url=f"https://arxiv.org/abs/{arxiv_id}",
                    language="en",
                    tags=["arxiv"]
                )
                
                papers.append(paper)
                
            except Exception as e:
                logger.warning(f"Failed to parse ArXiv entry: {e}")
                continue
        
        return papers
    
    def _parse_semantic_scholar_response(self, data: Dict[str, Any]) -> List[PaperMetadata]:
        """Parse Semantic Scholar API response.
        
        Args:
            data: JSON response data
            
        Returns:
            List of paper metadata
        """
        papers = []
        
        for item in data.get("data", []):
            paper = self._parse_semantic_scholar_paper(item)
            if paper:
                papers.append(paper)
        
        return papers
    
    def _parse_semantic_scholar_paper(self, item: Dict[str, Any]) -> Optional[PaperMetadata]:
        """Parse a single Semantic Scholar paper.
        
        Args:
            item: Paper data from API
            
        Returns:
            Paper metadata or None if parsing fails
        """
        try:
            title = item.get("title", "")
            abstract = item.get("abstract", "")
            year = item.get("year", datetime.now().year)
            
            # Authors
            authors = [
                author.get("name", "")
                for author in item.get("authors", [])
            ]
            
            # External IDs
            external_ids = item.get("externalIds", {})
            doi = external_ids.get("DOI")
            arxiv_id = external_ids.get("ArXiv")
            
            # Citation count
            citation_count = item.get("citationCount", 0)
            
            # Venue
            venue = item.get("venue", "")
            
            # PDF URL
            pdf_url = None
            open_access = item.get("openAccessPdf")
            if open_access:
                pdf_url = open_access.get("url")
            
            # Paper URL
            source_url = item.get("url", "")
            
            # Semantic Scholar ID
            ss_id = item.get("paperId")
            
            paper = PaperMetadata(
                title=title,
                title_en=title,
                authors=authors,
                authors_en=authors,
                abstract=abstract or "",
                abstract_en=abstract or "",
                doi=doi,
                arxiv_id=arxiv_id,
                semantic_scholar_id=ss_id,
                publication_year=year,
                publication_venue=venue,
                citation_count=citation_count,
                pdf_url=pdf_url,
                source_url=source_url,
                language="en",
                tags=["semantic_scholar"]
            )
            
            return paper
            
        except Exception as e:
            logger.warning(f"Failed to parse Semantic Scholar paper: {e}")
            return None
    
    def _deduplicate_papers(self, papers: List[PaperMetadata]) -> List[PaperMetadata]:
        """Remove duplicate papers based on DOI or ArXiv ID.
        
        Args:
            papers: List of papers
            
        Returns:
            Deduplicated list
        """
        seen = set()
        unique_papers = []
        
        for paper in papers:
            # Create identifier
            identifier = None
            if paper.doi:
                identifier = f"doi:{paper.doi}"
            elif paper.arxiv_id:
                identifier = f"arxiv:{paper.arxiv_id}"
            else:
                identifier = f"title:{paper.title}"
            
            if identifier not in seen:
                seen.add(identifier)
                unique_papers.append(paper)
        
        return unique_papers
    
    def enrich_paper_metadata(self, paper: PaperMetadata) -> PaperMetadata:
        """Enrich paper metadata by fetching from multiple sources.
        
        Args:
            paper: Paper with partial metadata
            
        Returns:
            Enriched paper metadata
        """
        # If we have DOI, try to get more info from Semantic Scholar
        if paper.doi and not paper.semantic_scholar_id:
            try:
                ss_paper = self.get_paper_by_doi(paper.doi)
                if ss_paper:
                    # Merge data, preferring non-empty values
                    paper.citation_count = ss_paper.citation_count or paper.citation_count
                    paper.semantic_scholar_id = ss_paper.semantic_scholar_id
                    if not paper.abstract:
                        paper.abstract = ss_paper.abstract
                    if not paper.pdf_url:
                        paper.pdf_url = ss_paper.pdf_url
            except Exception as e:
                logger.warning(f"Failed to enrich from Semantic Scholar: {e}")
        
        # If we have ArXiv ID but missing metadata, fetch from ArXiv
        if paper.arxiv_id and not paper.abstract:
            try:
                arxiv_paper = self.get_paper_by_arxiv_id(paper.arxiv_id)
                if arxiv_paper:
                    paper.abstract = arxiv_paper.abstract or paper.abstract
                    paper.pdf_url = arxiv_paper.pdf_url or paper.pdf_url
            except Exception as e:
                logger.warning(f"Failed to enrich from ArXiv: {e}")
        
        return paper
