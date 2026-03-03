"""
MCP Server entry point for GitHub MCP.

Exposes read-only GitHub tools over the Model Context Protocol (stdio transport).
"""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
)

from github_mcp.config import get_config
from github_mcp.tools import TOOLS, call_tool

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("github-mcp")

    @server.list_tools()
    async def list_tools() -> ListToolsResult:
        logger.info(f"Listing {len(TOOLS)} tools")
        return ListToolsResult(tools=TOOLS)

    @server.call_tool()
    async def handle_call_tool(
        name: str, arguments: dict[str, Any] | None
    ) -> CallToolResult:
        logger.info(f"Tool call: {name}")
        try:
            results = await call_tool(name, arguments or {})
            return CallToolResult(content=results)
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True,
            )

    return server


async def run_server() -> None:
    """Run the MCP server with stdio transport."""
    server = create_server()
    cfg = get_config()
    logger.info(
        "Starting GitHub MCP Server (api=%s, clone_dir=%s, token=%s)",
        cfg.api_url,
        cfg.clone_dir,
        "set" if cfg.token else "NOT SET",
    )

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    """CLI entry point."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
