"""
Agent CLI - Interactive command-line interface for the developer agent.

Split into submodules for readability:
- commands: Slash command handlers
- parser: Argument parsing
- runner: Interactive and non-interactive execution loops
"""

from .main import main

__all__ = ["main"]
