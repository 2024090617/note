"""Tool registry composition."""

from .base import BaseToolRegistry
from .file_ops import FileOpsMixin
from .search_ops import SearchOpsMixin
from .command_ops import CommandOpsMixin
from .environment_ops import EnvironmentOpsMixin


class ToolRegistry(
    BaseToolRegistry,
    FileOpsMixin,
    SearchOpsMixin,
    CommandOpsMixin,
    EnvironmentOpsMixin,
):
    """
    Registry of tools available to the agent.

    Tools are functions that perform actions like reading files,
    running commands, searching, etc.
    """

    pass
