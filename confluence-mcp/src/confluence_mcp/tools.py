"""
MCP Tool Definitions for Confluence

Defines all tools exposed by the MCP server.
"""

from typing import Any
from mcp.types import Tool, TextContent, ToolResult


def get_confluence_tools() -> list[Tool]:
    """Return all available Confluence tools"""
    return [
        Tool(
            name="confluence_get_page",
            description="Read a Confluence page by ID or title. Returns parsed content with support for multi-tabs and tables.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID (preferred method)"
                    },
                    "title": {
                        "type": "string",
                        "description": "Page title (requires space_key)"
                    },
                    "space_key": {
                        "type": "string",
                        "description": "Space key (required if using title)"
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown", "html"],
                        "description": "Output format (default: json)"
                    }
                },
                "required": ["space_key"]  # Either page_id or (title + space_key)
            }
        ),
        Tool(
            name="confluence_update_page",
            description="Update an existing Confluence page. Supports editing page title and content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID to update"
                    },
                    "title": {
                        "type": "string",
                        "description": "New page title (optional)"
                    },
                    "content": {
                        "type": "string",
                        "description": "New page content in storage format or plain text"
                    },
                    "version_comment": {
                        "type": "string",
                        "description": "Optional version history comment"
                    }
                },
                "required": ["page_id", "content"]
            }
        ),
        Tool(
            name="confluence_create_page",
            description="Create a new Confluence page in a space.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Page title"
                    },
                    "content": {
                        "type": "string",
                        "description": "Page content in storage format or plain text"
                    },
                    "space_key": {
                        "type": "string",
                        "description": "Space key to create page in"
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Optional parent page ID"
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional labels for the page"
                    }
                },
                "required": ["title", "content", "space_key"]
            }
        ),
        Tool(
            name="confluence_delete_page",
            description="Delete a Confluence page by ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID to delete"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="confluence_search",
            description="Search Confluence pages using CQL (Confluence Query Language) or text search.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (text or CQL)"
                    },
                    "space_key": {
                        "type": "string",
                        "description": "Optional space to limit search"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 25)",
                        "default": 25
                    },
                    "content_type": {
                        "type": "string",
                        "enum": ["page", "blogpost"],
                        "description": "Content type to search (default: page)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="confluence_get_children",
            description="Get child pages of a Confluence page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Parent page ID"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 100)"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="confluence_get_attachments",
            description="Get attachments for a Confluence page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="confluence_add_comment",
            description="Add a comment to a Confluence page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    },
                    "comment": {
                        "type": "string",
                        "description": "Comment text (can include HTML)"
                    }
                },
                "required": ["page_id", "comment"]
            }
        ),
        Tool(
            name="confluence_get_comments",
            description="Get all comments on a Confluence page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    }
                },
                "required": ["page_id"]
            }
        ),
        Tool(
            name="confluence_add_labels",
            description="Add labels to a Confluence page.",
            inputSchema={
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Page ID"
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to add"
                    }
                },
                "required": ["page_id", "labels"]
            }
        ),
        Tool(
            name="confluence_get_spaces",
            description="List all available Confluence spaces.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 100)"
                    }
                }
            }
        ),
    ]


def create_tool_result(success: bool, content: Any) -> ToolResult:
    """Create a MCP ToolResult"""
    if success:
        return ToolResult(
            content=[TextContent(type="text", text=str(content))],
            is_error=False
        )
    else:
        return ToolResult(
            content=[TextContent(type="text", text=str(content))],
            is_error=True
        )
