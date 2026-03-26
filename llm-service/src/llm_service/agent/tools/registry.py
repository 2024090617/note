"""Tool registry composition."""

from .base import BaseToolRegistry
from .file_ops import FileOpsMixin
from .search_ops import SearchOpsMixin
from .command_ops import CommandOpsMixin
from .environment_ops import EnvironmentOpsMixin
from .sandbox_ops import SandboxOpsMixin
from .mcp_ops import MCPOpsMixin
from .web_ops import WebOpsMixin


class ToolRegistry(
    BaseToolRegistry,
    FileOpsMixin,
    SearchOpsMixin,
    CommandOpsMixin,
    EnvironmentOpsMixin,
    SandboxOpsMixin,
    MCPOpsMixin,
    WebOpsMixin,
):
    """
    Registry of tools available to the agent.

    Tools are functions that perform actions like reading files,
    running commands, searching, MCP invocations, etc.
    """

    mcp_manager = None  # Set by the Agent when MCP is configured
