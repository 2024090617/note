"""Interactive and non-interactive execution loops."""

import json
import sys

from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from ..core import Agent
from .commands import CommandHandler
from .output import console


def run_interactive(agent: Agent):
    """Run interactive CLI loop."""
    handler = CommandHandler(agent)

    # Print welcome
    console.print(
        Panel(
            "[bold cyan]Developer Agent[/bold cyan]\n"
            f"Mode: {agent.config.mode.value} | Model: {agent.config.model}\n"
            "Type /help for commands or just chat.",
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

            # Handle slash commands
            if user_input.startswith("/"):
                if not handler.handle(user_input):
                    break
                continue

            # Regular chat
            with console.status("[bold blue]Thinking...", spinner="dots"):
                response = agent.chat(user_input)

            console.print(Panel(Markdown(response), title="[bold blue]Assistant[/bold blue]"))

        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/yellow]")
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run_non_interactive(agent: Agent, task: str, output_json: bool):
    """Run in non-interactive mode."""
    result = agent.run_task(task)

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
            "success": not bool(result.error),
            "summary": result.summary,
            "error": result.error,
            "actions": [a.to_dict() for a in agent.session.actions],
            "log": log_info,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.summary:
            print(result.summary)
        if result.error:
            print(f"\nError: {result.error}", file=sys.stderr)
            sys.exit(1)

        # Print log location
        print(
            f"\n[Log saved to: {agent.logger.log_dir}/interaction_{agent.session.id}_complete.json]",
            file=sys.stderr,
        )
