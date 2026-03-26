"""Interactive and non-interactive execution loops."""

import json
import sys

from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from ..core import Agent
from .output import console


def run_interactive(agent: Agent):
    """Run interactive CLI loop."""
    # Print welcome
    console.print(
        Panel(
            "[bold cyan]Developer Agent[/bold cyan]\n"
            f"Mode: {agent.config.mode.value} | Model: {agent.config.model}\n"
            "Describe your goal in natural language. The agent decides chat vs autonomous execution.",
            title="Welcome",
        )
    )

    # Check connection
    if not agent.check_connection():
        console.print("[yellow]⚠️  Not connected to Copilot Bridge.[/yellow]")
        console.print("Make sure VS Code is running with the Copilot Bridge extension")
        console.print("and run command: 'Start Copilot Bridge Server'")
        console.print()

    # Main loop
    while True:
        try:
            # Show status line
            status = agent.session.status_line()
            prompt = f"[dim]{status}[/dim]\n[bold green]>[/bold green] "

            user_input = Prompt.ask(prompt).strip()

            if not user_input:
                continue

            # Handle exit commands (with or without slash)
            if user_input.lower() in {"quit", "exit", "/quit", "/exit"}:
                console.print("[yellow]Goodbye![/yellow]")
                break

            with console.status("[bold blue]Thinking...", spinner="dots"):
                outcome = agent.respond(user_input)

            response_text = outcome.get("summary") or ""
            if outcome.get("error"):
                response_text = f"{response_text}\n\nError: {outcome['error']}"

            title = "[bold green]Task Result[/bold green]" if outcome.get("mode") == "task" else "[bold blue]Assistant[/bold blue]"
            console.print(Panel(Markdown(response_text), title=title))

        except KeyboardInterrupt:
            console.print("\n[yellow]Use quit or Ctrl+D to exit[/yellow]")
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run_non_interactive(agent: Agent, task: str, output_json: bool):
    """Run in non-interactive mode."""
    outcome = agent.respond(task, force_task=True)
    summary = outcome.get("summary")
    error = outcome.get("error")

    if output_json:
        # Include log info in JSON output
        log_info = None
        if agent.logger._current_interaction or agent.logger.log_dir.exists():
            log_info = {
                "log_dir": str(agent.logger.log_dir),
                "session_id": agent.session.id,
            }

        output = {
            "task": task,
            "success": not bool(error),
            "summary": summary,
            "error": error,
            "mode": outcome.get("mode"),
            "decision": outcome.get("decision"),
            "actions": [a.to_dict() for a in agent.session.actions],
            "log": log_info,
        }
        print(json.dumps(output, indent=2))
    else:
        if summary:
            print(summary)
        if error:
            print(f"\nError: {error}", file=sys.stderr)
            sys.exit(1)

        # Print log location
        print(
            f"\n[Log saved to: {agent.logger.log_dir}/interaction_{agent.session.id}_complete.json]",
            file=sys.stderr,
        )
