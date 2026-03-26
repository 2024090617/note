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
        default="claude-haiku-4.5",
        help="Model to use (default: claude-haiku-4.5)",
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
        "--sandbox",
        action="store_true",
        help="Enable Docker sandbox for script execution",
    )

    parser.add_argument(
        "--sandbox-image",
        default="python:3.12-slim",
        help="Default Docker image for sandbox (default: python:3.12-slim)",
    )

    parser.add_argument(
        "--mcp-config",
        help="Path to MCP servers config file (mcp.json)",
    )

    parser.add_argument(
        "--enable-delegation",
        action="store_true",
        help="Enable specialist delegation for reviewing candidate solutions",
    )

    parser.add_argument(
        "--max-specialists",
        type=int,
        default=3,
        help="Maximum number of specialist reviewers (default: 3)",
    )

    parser.add_argument(
        "--max-candidate-pages",
        type=int,
        default=5,
        help="Maximum candidate pages sent to delegation review (default: 5)",
    )

    parser.add_argument(
        "--max-collab-rounds",
        type=int,
        default=1,
        help="Maximum specialist collaboration rounds (default: 1)",
    )

    parser.add_argument(
        "--memory-strategy",
        choices=["claude-code", "openclaw", "none"],
        default="claude-code",
        help="Memory strategy (default: claude-code)",
    )

    parser.add_argument(
        "--memory-dir",
        help="Directory for memory storage (default: <workdir>/.agent/memory)",
    )

    parser.add_argument(
        "--web-timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds for online read/download tools (default: 20)",
    )

    parser.add_argument(
        "--web-max-read-bytes",
        type=int,
        default=2 * 1024 * 1024,
        help="Max response bytes fetched for read_online_content (default: 2097152)",
    )

    parser.add_argument(
        "--web-max-read-chars",
        type=int,
        default=20000,
        help="Max text chars returned by read_online_content (default: 20000)",
    )

    parser.add_argument(
        "--web-max-download-bytes",
        type=int,
        default=50 * 1024 * 1024,
        help="Max bytes allowed for download_remote_resource (default: 52428800)",
    )

    parser.add_argument(
        "--allow-private-hosts",
        action="store_true",
        help="Allow localhost/private network targets for web tools (unsafe)",
    )

    parser.add_argument(
        "--no-memory",
        action="store_true",
        help="Disable memory (shorthand for --memory-strategy none)",
    )

    parser.add_argument(
        "task",
        nargs="*",
        help="Task to run (non-interactive mode)",
    )

    return parser
