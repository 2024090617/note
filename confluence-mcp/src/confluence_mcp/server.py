"""
Confluence MCP Server

A Model Context Protocol server that provides tools to interact with Confluence.
Supports both Confluence Cloud and Server/Data Center.
"""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    TextContent,
    Tool,
    ListToolsResult,
)

from .config import ConfluenceConfig
from .client import ConfluenceClient
from .parser import ContentParser
from .tools import get_confluence_tools, create_tool_result

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfluenceMCPServer:
    """MCP Server for Confluence operations"""
    
    def __init__(self, config: ConfluenceConfig):
        self.config = config
        self.server = Server("confluence-mcp")
        self.client: ConfluenceClient | None = None
        self.parser = ContentParser()
        
        # Register handlers
        self.server.list_tools(self.list_tools)
        self.server.call_tool(self.call_tool)
    
    async def initialize(self):
        """Initialize the MCP server"""
        # Validate configuration
        errors = self.config.validate()
        if errors:
            logger.error("Configuration errors:")
            for error in errors:
                logger.error(f"  - {error}")
            raise ValueError("Invalid configuration")
        
        # Create client
        self.client = ConfluenceClient(self.config)
        await self.client.connect()
        
        logger.info(f"Connected to Confluence: {self.config.base_url}")
    
    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.close()
    
    async def list_tools(self) -> ListToolsResult:
        """List all available tools"""
        return ListToolsResult(tools=get_confluence_tools())
    
    async def call_tool(self, request: CallToolRequest) -> CallToolResult:
        """Handle tool calls"""
        tool_name = request.name
        args = request.arguments
        
        try:
            if tool_name == "confluence_get_page":
                result = await self._get_page(args)
            elif tool_name == "confluence_update_page":
                result = await self._update_page(args)
            elif tool_name == "confluence_create_page":
                result = await self._create_page(args)
            elif tool_name == "confluence_delete_page":
                result = await self._delete_page(args)
            elif tool_name == "confluence_search":
                result = await self._search(args)
            elif tool_name == "confluence_get_children":
                result = await self._get_children(args)
            elif tool_name == "confluence_get_attachments":
                result = await self._get_attachments(args)
            elif tool_name == "confluence_add_comment":
                result = await self._add_comment(args)
            elif tool_name == "confluence_get_comments":
                result = await self._get_comments(args)
            elif tool_name == "confluence_add_labels":
                result = await self._add_labels(args)
            elif tool_name == "confluence_get_spaces":
                result = await self._get_spaces(args)
            else:
                return create_tool_result(False, f"Unknown tool: {tool_name}")
            
            return create_tool_result(True, result)
        
        except Exception as e:
            logger.exception(f"Error calling tool {tool_name}")
            return create_tool_result(False, f"Error: {str(e)}")
    
    # =========================================================================
    # Tool Implementations
    # =========================================================================
    
    async def _get_page(self, args: dict) -> dict:
        """Get a Confluence page"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args.get("page_id")
        title = args.get("title")
        space_key = args.get("space_key")
        format_type = args.get("format", "json")
        
        page = await self.client.get_page(
            page_id=page_id,
            title=title,
            space_key=space_key
        )
        
        # Parse content
        parsed = self.parser.parse(page.body_storage)
        
        if format_type == "markdown":
            return {
                "id": page.id,
                "title": page.title,
                "url": page.url,
                "space": page.space_key,
                "version": page.version,
                "content": self.parser.extract_markdown(),
                "format": "markdown",
            }
        elif format_type == "html":
            return {
                "id": page.id,
                "title": page.title,
                "url": page.url,
                "space": page.space_key,
                "version": page.version,
                "content": page.body_view,
                "format": "html",
            }
        else:  # json
            return {
                "id": page.id,
                "title": page.title,
                "url": page.url,
                "space": page.space_key,
                "version": page.version,
                "labels": page.labels,
                "content": parsed,
                "format": "json",
            }
    
    async def _create_page(self, args: dict) -> dict:
        """Create a new page"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        title = args["title"]
        content = args["content"]
        space_key = args["space_key"]
        parent_id = args.get("parent_id")
        labels = args.get("labels")
        
        page = await self.client.create_page(
            title=title,
            body=content,
            space_key=space_key,
            parent_id=parent_id,
            labels=labels,
        )
        
        return {
            "id": page.id,
            "title": page.title,
            "url": page.url,
            "space": page.space_key,
            "version": page.version,
            "status": "created",
        }
    
    async def _update_page(self, args: dict) -> dict:
        """Update a page"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        title = args.get("title")
        content = args.get("content")
        version_comment = args.get("version_comment")
        
        page = await self.client.update_page(
            page_id=page_id,
            title=title,
            body=content,
            version_comment=version_comment,
        )
        
        return {
            "id": page.id,
            "title": page.title,
            "url": page.url,
            "version": page.version,
            "status": "updated",
        }
    
    async def _delete_page(self, args: dict) -> dict:
        """Delete a page"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        success = await self.client.delete_page(page_id)
        
        return {
            "page_id": page_id,
            "status": "deleted" if success else "failed",
        }
    
    async def _search(self, args: dict) -> dict:
        """Search Confluence"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        query = args["query"]
        space_key = args.get("space_key")
        limit = args.get("limit", 25)
        content_type = args.get("content_type", "page")
        
        results = await self.client.search(
            query=query,
            space_key=space_key,
            limit=limit,
            content_type=content_type,
        )
        
        return {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "id": r.id,
                    "title": r.title,
                    "space": r.space_key,
                    "url": r.url,
                    "excerpt": r.excerpt,
                }
                for r in results
            ],
        }
    
    async def _get_children(self, args: dict) -> dict:
        """Get child pages"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        limit = args.get("limit", 100)
        
        children = await self.client.get_child_pages(page_id, limit)
        
        return {
            "page_id": page_id,
            "count": len(children),
            "children": children,
        }
    
    async def _get_attachments(self, args: dict) -> dict:
        """Get page attachments"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        
        attachments = await self.client.get_attachments(page_id)
        
        return {
            "page_id": page_id,
            "count": len(attachments),
            "attachments": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "media_type": a.media_type,
                    "size": a.file_size,
                    "url": a.download_url,
                }
                for a in attachments
            ],
        }
    
    async def _add_comment(self, args: dict) -> dict:
        """Add a comment"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        comment = args["comment"]
        
        result = await self.client.add_comment(page_id, comment)
        
        return {
            "page_id": page_id,
            "comment_id": result["id"],
            "status": "added",
        }
    
    async def _get_comments(self, args: dict) -> dict:
        """Get page comments"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        
        comments = await self.client.get_comments(page_id)
        
        return {
            "page_id": page_id,
            "count": len(comments),
            "comments": comments,
        }
    
    async def _add_labels(self, args: dict) -> dict:
        """Add labels to page"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        page_id = args["page_id"]
        labels = args["labels"]
        
        success = await self.client.add_labels(page_id, labels)
        
        return {
            "page_id": page_id,
            "labels": labels,
            "status": "added" if success else "failed",
        }
    
    async def _get_spaces(self, args: dict) -> dict:
        """Get list of spaces"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        limit = args.get("limit", 100)
        
        spaces = await self.client.get_spaces(limit)
        
        return {
            "count": len(spaces),
            "spaces": spaces,
        }


async def run_server(config: ConfluenceConfig):
    """Run the MCP server"""
    server = ConfluenceMCPServer(config)
    
    try:
        await server.initialize()
        logger.info("Starting Confluence MCP server...")
        async with stdio_server(server.server) as (read_stream, write_stream):
            await server.server.run(
                read_stream,
                write_stream,
                await asyncio.get_running_loop().create_task(
                    asyncio.Event().wait()
                )
            )
    finally:
        await server.cleanup()


def main():
    """Entry point for CLI"""
    import sys
    from dotenv import load_dotenv
    
    load_dotenv()
    
    config = ConfluenceConfig.from_env()
    
    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        logger.info("Server shut down by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Server error")
        sys.exit(1)


if __name__ == "__main__":
    main()
