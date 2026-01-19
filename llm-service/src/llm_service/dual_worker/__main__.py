#!/usr/bin/env python3
"""
Entry point for dual-worker CLI.

Usage:
    python -m llm_service.dual_worker.cli [command] [options]

Or after installation:
    dw [command] [options]
"""

from llm_service.dual_worker.cli import cli

if __name__ == "__main__":
    cli()
