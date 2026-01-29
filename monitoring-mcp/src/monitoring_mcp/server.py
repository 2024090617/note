"""
MCP Server implementation for monitoring tools.

Provides a Model Context Protocol server that exposes monitoring
tools for Splunk, AppDynamics, Kafka, and MongoDB.
"""

import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    ListToolsResult,
    CallToolResult,
    TextContent,
)

from monitoring_mcp.config import get_config
from monitoring_mcp.tools import TOOLS, call_tool

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("monitoring-mcp")
    
    @server.list_tools()
    async def list_tools() -> ListToolsResult:
        """Return list of available monitoring tools."""
        config = get_config()
        enabled_services = config.get_enabled_services()
        
        # Filter tools based on enabled services
        available_tools = []
        for tool in TOOLS:
            # Map tool names to services
            if tool.name.startswith("search_splunk") or tool.name.startswith("get_splunk"):
                if "splunk" in enabled_services or not config.splunk.base_url:
                    available_tools.append(tool)
            elif tool.name.startswith("get_jvm") or tool.name.startswith("get_business"):
                if "appdynamics" in enabled_services or not config.appdynamics.base_url:
                    available_tools.append(tool)
            elif tool.name.startswith("check_kafka") or tool.name.startswith("get_kafka"):
                if "kafka" in enabled_services or not config.kafka.bootstrap_servers:
                    available_tools.append(tool)
            elif tool.name.startswith("get_mongodb") or tool.name.startswith("check_mongodb"):
                if "mongodb" in enabled_services or not config.mongodb.uri:
                    available_tools.append(tool)
            else:
                # Utility tools always available
                available_tools.append(tool)
        
        logger.info(f"Listing {len(available_tools)} tools (enabled services: {enabled_services})")
        return ListToolsResult(tools=available_tools)
    
    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        """Handle tool invocation."""
        logger.info(f"Tool call: {name} with args: {arguments}")
        
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


async def run_server():
    """Run the MCP server."""
    server = create_server()
    
    config = get_config()
    enabled = config.get_enabled_services()
    logger.info(f"Starting Monitoring MCP Server (enabled services: {enabled})")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main():
    """Entry point for the MCP server."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
