"""Click CLI entrypoint for digimate."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import click

from digimate import __version__

# Set up LLM debug logger → writes to .digimate/log/llm-log-<datetime>.log
_llm_logger = logging.getLogger("digimate.llm")
_llm_logger.setLevel(logging.DEBUG)
_log_dir = Path(".digimate/log")
_log_dir.mkdir(parents=True, exist_ok=True)
_llm_log_file = _log_dir / f"llm-log-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
_fh = logging.FileHandler(_llm_log_file, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
_llm_logger.addHandler(_fh)


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="digimate")
@click.option("-i", "--interactive", is_flag=True, help="Start interactive chat mode.")
@click.option("--backend", type=click.Choice(["copilot", "openai"]), default=None,
              help="LLM backend to use.")
@click.option("--model", default=None, help="Model name override.")
@click.option("--api-base", default=None, help="OpenAI-compatible API base URL.")
@click.option("--api-key", default=None, help="API key (or set OPENAI_API_KEY).")
@click.option("--workdir", default=None, help="Working directory.")
@click.option("--no-trace", is_flag=True, help="Disable stderr trace output.")
@click.option("--json", "output_json", is_flag=True, help="Output JSON (non-interactive only).")
@click.option("--mcp-config", default=None, help="Path to MCP config JSON.")
@click.argument("task", required=False)
@click.pass_context
def cli(ctx, interactive, backend, model, api_base, api_key, workdir, no_trace, output_json, mcp_config, task):
    """Digimate — lightweight developer agent."""
    if ctx.invoked_subcommand is not None:
        return

    from digimate.core.config import AgentConfig
    from digimate.core.agent import Agent
    from digimate.cli.runner import run_interactive, run_non_interactive

    # Start from env vars, then overlay explicit CLI flags
    cfg = AgentConfig.from_env()
    if backend is not None:
        cfg.backend = backend
    if model is not None:
        cfg.model = model
    if api_base is not None:
        cfg.api_base = api_base
    if api_key is not None:
        cfg.api_key = api_key
    elif not cfg.api_key:
        cfg.api_key = os.environ.get("OPENAI_API_KEY")
    if workdir is not None:
        cfg.workdir = str(os.path.abspath(workdir))
    if no_trace:
        cfg.trace_stderr = False
        cfg.trace_file = False
    if mcp_config is not None:
        cfg.mcp_config_path = mcp_config

    agent = Agent(cfg)

    if interactive:
        run_interactive(agent)
        return

    if task:
        run_non_interactive(agent, task, output_json=output_json)
        return

    # No subcommand, no flags → show help
    click.echo(ctx.get_help())


@cli.command()
def version():
    """Show version info."""
    click.echo(f"digimate {__version__}")
