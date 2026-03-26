"""Agent memory — multi-strategy persistent memory system.

Supports pluggable memory strategies:

- **claude-code** (default): Hierarchical CLAUDE.md instruction files + auto-memory
  MEMORY.md with keyword search.  Zero extra dependencies.
- **openclaw**: Daily logs + curated MEMORY.md + hybrid BM25/vector search via
  SQLite.  Optional deps: ``sqlite-vec``, ``sentence-transformers``.
- **none**: Memory disabled.

Usage::

    from llm_service.agent.memory import create_memory_manager

    manager = create_memory_manager("claude-code", memory_dir=".digimate/memory", workdir=".")
    manager.initialize()
    print(manager.get_prompt_context())
"""

import logging
from pathlib import Path
from typing import Optional

from .base import MemoryEntry, MemoryStrategy

logger = logging.getLogger(__name__)

# Re-export public types
__all__ = [
    "MemoryEntry",
    "MemoryStrategy",
    "create_memory_manager",
]


def create_memory_manager(
    strategy: str = "claude-code",
    memory_dir: Optional[str] = None,
    workdir: str = ".",
) -> Optional[MemoryStrategy]:
    """
    Factory — create and initialize a memory strategy.

    Args:
        strategy: ``"claude-code"`` | ``"openclaw"`` | ``"none"``.
        memory_dir: Directory for persistent memory files.
                    Defaults to ``<workdir>/.digimate/memory``.
        workdir: Agent working directory (project root).

    Returns:
        Initialized MemoryStrategy, or None if *strategy* is ``"none"``.
    """
    if strategy == "none":
        return None

    if memory_dir is None:
        memory_dir = str(Path(workdir).resolve() / ".digimate" / "memory")

    if strategy == "claude-code":
        from .claude_code import ClaudeCodeMemory

        mgr = ClaudeCodeMemory(memory_dir=memory_dir, workdir=workdir)
    elif strategy == "openclaw":
        from .openclaw import OpenClawMemory

        mgr = OpenClawMemory(memory_dir=memory_dir, workdir=workdir)
    else:
        logger.warning("Unknown memory strategy '%s', falling back to claude-code", strategy)
        from .claude_code import ClaudeCodeMemory

        mgr = ClaudeCodeMemory(memory_dir=memory_dir, workdir=workdir)

    try:
        mgr.initialize()
    except Exception as e:
        logger.warning("Memory initialization failed: %s", e)
        return None

    return mgr
