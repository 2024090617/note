"""Argument parser for the agent CLI."""

import argparse
from pathlib import Path


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Developer Agent - Autonomous software development assistant",
    )

    parser.add_argument(
        "--mode",
        "-m",
        choices=["copilot", "github-models"],
        default="copilot",
        help="Backend mode (default: copilot)",
    )

    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Model to use (default: gpt-4o-mini)",
    )

    parser.add_argument(
        "--system",
        "-s",
        help="System prompt (or @file to load from file)",
    )

    parser.add_argument(
        "--workdir",
        "-w",
        default=str(Path.cwd()),
        help="Working directory (default: current directory)",
    )

    parser.add_argument(
        "--non-interactive",
        "-n",
        action="store_true",
        help="Non-interactive mode",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (with --non-interactive)",
    )

    parser.add_argument(
        "--log-dir",
        help="Directory for log files (default: ./agent_logs)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose console logging",
    )

    parser.add_argument(
        "--no-log-file",
        action="store_true",
        help="Disable file logging",
    )

    parser.add_argument(
        "task",
        nargs="*",
        help="Task to run (non-interactive mode)",
    )

    return parser
