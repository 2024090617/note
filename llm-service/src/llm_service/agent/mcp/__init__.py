"""MCP (Model Context Protocol) integration for the agent.

Provides the ability to connect to MCP servers, discover their tools,
and invoke them from within the ReAct agent loop.

MCP servers are configured via a JSON config file (mcp.json):

    {
        "mcpServers": {
            "monitoring": {
                "command": "monitoring-mcp",
                "args": [],
                "env": {}
            }
        }
    }
"""

from .client import MCPManager, MCPConnection, MCPToolInfo, MCPServerConfig

__all__ = [
    "MCPManager",
    "MCPConnection",
    "MCPToolInfo",
    "MCPServerConfig",
]
