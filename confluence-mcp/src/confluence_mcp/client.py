"""
Confluence REST API Client

Handles all API interactions with Confluence Cloud and Server/Data Center.
"""

import asyncio
from typing import Any, Optional
from dataclasses import dataclass
import httpx

from .config import ConfluenceConfig, ConfluenceType


@dataclass
class Page:
    """Represents a Confluence page"""
    id: str
    title: str
    space_key: str
    version: int
    body_storage: str  # Storage format (XHTML)
    body_view: str     # Rendered HTML
    url: str
    parent_id: Optional[str] = None
    labels: list[str] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = []


@dataclass
class SearchResult:
    """Represents a search result"""
    id: str
    title: str
    space_key: str
    url: str
    excerpt: str
    last_modified: str


@dataclass
class Attachment:
    """Represents a page attachment"""
    id: str
    title: str
    filename: str
    media_type: str
    file_size: int
    download_url: str


class ConfluenceClient:
    """Async client for Confluence REST API"""
    
    def __init__(self, config: ConfluenceConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def connect(self):
        """Initialize HTTP client"""
        self._client = httpx.AsyncClient(
            headers={
                **self.config.auth_headers,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(self.config.timeout),
        )
    
    async def close(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Client not connected. Use 'async with' or call connect()")
        return self._client
    
    # =========================================================================
    # Page Operations
    # =========================================================================
    
    async def get_page(
        self,
        page_id: Optional[str] = None,
        title: Optional[str] = None,
        space_key: Optional[str] = None,
    ) -> Page:
        """
        Get a Confluence page by ID or by title+space.
        
        Args:
            page_id: Page ID (preferred)
            title: Page title (requires space_key)
            space_key: Space key (required if using title)
        
        Returns:
            Page object with content
        """
        if page_id:
            return await self._get_page_by_id(page_id)
        elif title and space_key:
            return await self._get_page_by_title(title, space_key)
        else:
            raise ValueError("Either page_id or (title + space_key) required")
    
    async def _get_page_by_id(self, page_id: str) -> Page:
        """Get page by ID"""
        expand = "body.storage,body.view,version,space,ancestors"
        url = f"{self.config.api_base}/content/{page_id}?expand={expand}"
        
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        
        return self._parse_page(data)
    
    async def _get_page_by_title(self, title: str, space_key: str) -> Page:
        """Get page by title and space"""
        expand = "body.storage,body.view,version,ancestors"
        url = f"{self.config.api_base}/content"
        params = {
            "spaceKey": space_key,
            "title": title,
            "expand": expand,
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data.get("results"):
            raise ValueError(f"Page not found: {title} in space {space_key}")
        
        return self._parse_page(data["results"][0])
    
    def _parse_page(self, data: dict) -> Page:
        """Parse API response into Page object"""
        base_url = self.config.base_url.rstrip("/")
        
        # Handle different URL formats
        if "_links" in data:
            web_ui = data["_links"].get("webui", "")
            if self.config.confluence_type == ConfluenceType.CLOUD:
                url = f"{base_url}/wiki{web_ui}"
            else:
                url = f"{base_url}{web_ui}"
        else:
            url = f"{base_url}/pages/{data['id']}"
        
        # Get parent ID
        parent_id = None
        if data.get("ancestors"):
            parent_id = data["ancestors"][-1]["id"]
        
        return Page(
            id=data["id"],
            title=data["title"],
            space_key=data.get("space", {}).get("key", ""),
            version=data.get("version", {}).get("number", 1),
            body_storage=data.get("body", {}).get("storage", {}).get("value", ""),
            body_view=data.get("body", {}).get("view", {}).get("value", ""),
            url=url,
            parent_id=parent_id,
            labels=[
                label["name"] 
                for label in data.get("metadata", {}).get("labels", {}).get("results", [])
            ],
        )
    
    async def create_page(
        self,
        title: str,
        body: str,
        space_key: str,
        parent_id: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> Page:
        """
        Create a new Confluence page.
        
        Args:
            title: Page title
            body: Page content in storage format (XHTML) or will be converted
            space_key: Space key to create page in
            parent_id: Optional parent page ID
            labels: Optional list of labels
        
        Returns:
            Created Page object
        """
        url = f"{self.config.api_base}/content"
        
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": body,
                    "representation": "storage",
                }
            },
        }
        
        if parent_id:
            payload["ancestors"] = [{"id": parent_id}]
        
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        page = self._parse_page(data)
        
        # Add labels if provided
        if labels:
            await self.add_labels(page.id, labels)
        
        return page
    
    async def update_page(
        self,
        page_id: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        version_comment: Optional[str] = None,
    ) -> Page:
        """
        Update an existing Confluence page.
        
        Args:
            page_id: Page ID to update
            title: New title (optional, keeps existing if not provided)
            body: New body content in storage format
            version_comment: Optional version comment
        
        Returns:
            Updated Page object
        """
        # Get current page to get version number
        current = await self.get_page(page_id=page_id)
        
        url = f"{self.config.api_base}/content/{page_id}"
        
        payload = {
            "type": "page",
            "title": title or current.title,
            "version": {
                "number": current.version + 1,
            },
            "body": {
                "storage": {
                    "value": body if body is not None else current.body_storage,
                    "representation": "storage",
                }
            },
        }
        
        if version_comment:
            payload["version"]["message"] = version_comment
        
        response = await self.client.put(url, json=payload)
        response.raise_for_status()
        
        return await self.get_page(page_id=page_id)
    
    async def delete_page(self, page_id: str) -> bool:
        """Delete a Confluence page"""
        url = f"{self.config.api_base}/content/{page_id}"
        response = await self.client.delete(url)
        return response.status_code == 204
    
    # =========================================================================
    # Search Operations
    # =========================================================================
    
    async def search(
        self,
        query: str,
        space_key: Optional[str] = None,
        limit: int = 25,
        content_type: str = "page",
    ) -> list[SearchResult]:
        """
        Search Confluence using CQL.
        
        Args:
            query: Search text or CQL query
            space_key: Limit search to space
            limit: Maximum results
            content_type: Type of content (page, blogpost, etc.)
        
        Returns:
            List of SearchResult objects
        """
        # Build CQL query
        cql_parts = [f'type="{content_type}"']
        
        if space_key:
            cql_parts.append(f'space="{space_key}"')
        
        # If query looks like CQL, use it directly
        if any(op in query for op in ["=", "~", "AND", "OR"]):
            cql_parts.append(f"({query})")
        else:
            # Text search
            cql_parts.append(f'text~"{query}"')
        
        cql = " AND ".join(cql_parts)
        
        url = f"{self.config.api_base}/content/search"
        params = {
            "cql": cql,
            "limit": limit,
            "expand": "space",
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            base_url = self.config.base_url.rstrip("/")
            web_ui = item.get("_links", {}).get("webui", "")
            
            if self.config.confluence_type == ConfluenceType.CLOUD:
                url = f"{base_url}/wiki{web_ui}"
            else:
                url = f"{base_url}{web_ui}"
            
            results.append(SearchResult(
                id=item["id"],
                title=item["title"],
                space_key=item.get("space", {}).get("key", ""),
                url=url,
                excerpt=item.get("excerpt", ""),
                last_modified=item.get("lastModified", ""),
            ))
        
        return results
    
    # =========================================================================
    # Child Pages
    # =========================================================================
    
    async def get_child_pages(
        self,
        page_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """Get child pages of a page"""
        url = f"{self.config.api_base}/content/{page_id}/child/page"
        params = {"limit": limit, "expand": "version"}
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        return [
            {
                "id": child["id"],
                "title": child["title"],
                "version": child.get("version", {}).get("number", 1),
            }
            for child in data.get("results", [])
        ]
    
    # =========================================================================
    # Attachments
    # =========================================================================
    
    async def get_attachments(self, page_id: str) -> list[Attachment]:
        """Get attachments for a page"""
        url = f"{self.config.api_base}/content/{page_id}/child/attachment"
        
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        
        base_url = self.config.base_url.rstrip("/")
        attachments = []
        
        for item in data.get("results", []):
            download_path = item.get("_links", {}).get("download", "")
            if self.config.confluence_type == ConfluenceType.CLOUD:
                download_url = f"{base_url}/wiki{download_path}"
            else:
                download_url = f"{base_url}{download_path}"
            
            attachments.append(Attachment(
                id=item["id"],
                title=item["title"],
                filename=item["title"],
                media_type=item.get("metadata", {}).get("mediaType", ""),
                file_size=item.get("extensions", {}).get("fileSize", 0),
                download_url=download_url,
            ))
        
        return attachments
    
    # =========================================================================
    # Labels
    # =========================================================================
    
    async def add_labels(self, page_id: str, labels: list[str]) -> bool:
        """Add labels to a page"""
        url = f"{self.config.api_base}/content/{page_id}/label"
        
        payload = [{"name": label} for label in labels]
        
        response = await self.client.post(url, json=payload)
        return response.status_code == 200
    
    # =========================================================================
    # Spaces
    # =========================================================================
    
    async def get_spaces(self, limit: int = 100) -> list[dict]:
        """Get list of spaces"""
        url = f"{self.config.api_base}/space"
        params = {"limit": limit}
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        return [
            {
                "key": space["key"],
                "name": space["name"],
                "type": space.get("type", "global"),
            }
            for space in data.get("results", [])
        ]
    
    # =========================================================================
    # Comments
    # =========================================================================
    
    async def add_comment(self, page_id: str, comment: str) -> dict:
        """Add a comment to a page"""
        url = f"{self.config.api_base}/content"
        
        payload = {
            "type": "comment",
            "container": {"id": page_id, "type": "page"},
            "body": {
                "storage": {
                    "value": f"<p>{comment}</p>",
                    "representation": "storage",
                }
            },
        }
        
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        return {"id": data["id"], "body": comment}
    
    async def get_comments(self, page_id: str) -> list[dict]:
        """Get comments for a page"""
        url = f"{self.config.api_base}/content/{page_id}/child/comment"
        params = {"expand": "body.storage"}
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        return [
            {
                "id": comment["id"],
                "body": comment.get("body", {}).get("storage", {}).get("value", ""),
            }
            for comment in data.get("results", [])
        ]
