"""
Confluence MCP Server

A Model Context Protocol server for Atlassian Confluence that handles
complex content elements like multi-tabs, tables, and macros.
"""

from .server import main, create_server
from .client import ConfluenceClient
from .parser import ContentParser, TabGroup, Table, TableRow, TableCell
from .config import ConfluenceConfig

__version__ = "0.1.0"

__all__ = [
    "main",
    "create_server",
    "ConfluenceClient",
    "ContentParser",
    "ConfluenceConfig",
    "TabGroup",
    "Table",
    "TableRow",
    "TableCell",
]
