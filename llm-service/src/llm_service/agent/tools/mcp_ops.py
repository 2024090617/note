"""MCP operations mixin — exposes MCP tools to the agent."""

import json
from typing import Any, Dict, List, Optional

from .types import ToolResult


class MCPOpsMixin:
    """
    Mixin that provides MCP (Model Context Protocol) tool operations.

    Requires self.mcp_manager to be set (MCPManager instance or None).
    """

    mcp_manager: Any  # MCPManager | None — set by the Agent

    def mcp_list_servers(self) -> ToolResult:
        """List configured MCP servers."""
        if not self.mcp_manager:
            return ToolResult(False, "", "MCP not configured. Use --mcp-config to provide a config file.")

        servers = self.mcp_manager.list_servers()
        if not servers:
            return ToolResult(True, "No MCP servers configured.")

        return ToolResult(True, f"Configured MCP servers: {', '.join(servers)}")

    def mcp_list_tools(self, server: Optional[str] = None) -> ToolResult:
        """
        List tools from one or all MCP servers.

        Args:
            server: Specific server name, or None for all.
        """
        if not self.mcp_manager:
            return ToolResult(False, "", "MCP not configured. Use --mcp-config to provide a config file.")

        try:
            tools = self.mcp_manager.list_tools(server=server)
        except Exception as e:
            return ToolResult(False, "", f"Failed to list MCP tools: {e}")

        if not tools:
            scope = f"server '{server}'" if server else "any server"
            return ToolResult(True, f"No tools found on {scope}.")

        lines = [f"MCP tools ({len(tools)}):"]
        current_server = None
        for t in tools:
            if t.server_name != current_server:
                current_server = t.server_name
                lines.append(f"\n  [{current_server}]")
            params_summary = ""
            props = t.input_schema.get("properties", {})
            if props:
                param_names = list(props.keys())
                params_summary = f" — params: {', '.join(param_names)}"
            lines.append(f"    - {t.name}: {t.description}{params_summary}")

        return ToolResult(True, "\n".join(lines))

    def mcp_call_tool(
        self,
        server: str,
        tool: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Call a tool on an MCP server.

        Args:
            server: MCP server name.
            tool: Tool name to invoke.
            arguments: Tool arguments dict.
        """
        if not self.mcp_manager:
            return ToolResult(False, "", "MCP not configured. Use --mcp-config to provide a config file.")

        if not server:
            return ToolResult(False, "", "server is required")
        if not tool:
            return ToolResult(False, "", "tool is required")

        try:
            result = self.mcp_manager.call_tool(server, tool, arguments or {})
            return ToolResult(True, result)
        except ValueError as e:
            return ToolResult(False, "", str(e))
        except RuntimeError as e:
            return ToolResult(False, "", f"MCP tool call failed: {e}")
        except Exception as e:
            return ToolResult(False, "", f"Unexpected error calling MCP tool: {e}")
