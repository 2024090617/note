"""
Agent CLI - Interactive command-line interface for the developer agent.

Provides a TUI/CLI loop with slash commands for controlling the agent.
"""

import sys
import os
import json
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.syntax import Syntax
from rich.live import Live

from .core import Agent, AgentConfig, AgentMode, AgentResponse
from .copilot_client import CopilotBridgeError
from .session import Session


console = Console()


# ==================== Slash Command Handlers ====================

class CommandHandler:
    """Handler for slash commands."""
    
    def __init__(self, agent: Agent):
        self.agent = agent
        self.commands = {
            "help": self.cmd_help,
            "quit": self.cmd_quit,
            "exit": self.cmd_quit,
            "status": self.cmd_status,
            "mode": self.cmd_mode,
            "model": self.cmd_model,
            "system": self.cmd_system,
            "task": self.cmd_task,
            "open": self.cmd_open,
            "search": self.cmd_search,
            "diff": self.cmd_diff,
            "save": self.cmd_save,
            "load": self.cmd_load,
            "env": self.cmd_env,
            "lint": self.cmd_lint,
            "test": self.cmd_test,
            "run": self.cmd_run,
            "confirm": self.cmd_confirm,
            "rollback": self.cmd_rollback,
            "clear": self.cmd_clear,
            "models": self.cmd_models,
            "logs": self.cmd_logs,
        }
    
    def handle(self, command: str) -> bool:
        """
        Handle a slash command.
        
        Returns:
            True if should continue loop, False to exit
        """
        parts = command[1:].split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        handler = self.commands.get(cmd_name)
        if handler:
            return handler(args)
        else:
            console.print(f"[red]Unknown command: /{cmd_name}[/red]")
            console.print("Type /help for available commands.")
            return True
    
    def cmd_help(self, args: str) -> bool:
        """Show help."""
        help_text = """
[bold cyan]Developer Agent Commands[/bold cyan]

[bold]General:[/bold]
  /help              Show this help message
  /quit, /exit       Exit the agent
  /status            Show current mode, model, workdir, git status
  /clear             Clear conversation history

[bold]Configuration:[/bold]
  /mode <copilot|github-models>   Switch backend mode
  /model <name>                   Set model (e.g., gpt-4o, claude-3.5-sonnet)
  /system <text|@file>            Set system prompt
  /models                         List available models

[bold]Task Management:[/bold]
  /task <description|@file>       Start a new autonomous task
  /save <path>                    Save session to file
  /load <path>                    Load session from file

[bold]File Operations:[/bold]
  /open <path>                    Preview a file
  /search <pattern>               Search workspace for files/content
  /diff                           Show pending changes

[bold]Developer Tools:[/bold]
  /env                            Detect development environment
  /lint [cmd]                     Run linter (default: ruff/eslint)
  /test [cmd]                     Run tests (default: pytest/npm test)
  /run <cmd>                      Run shell command (confirms risky commands)
  /confirm                        Confirm pending risky action
  /rollback                       Revert uncommitted changes (requires confirm)
  /logs [session_id]              List or view interaction logs

[bold]Chat Mode:[/bold]
  Just type your message without a slash to chat with the agent.
"""
        console.print(Panel(help_text, title="Help"))
        return True
    
    def cmd_quit(self, args: str) -> bool:
        """Exit the agent."""
        console.print("[yellow]Goodbye![/yellow]")
        return False
    
    def cmd_status(self, args: str) -> bool:
        """Show status."""
        status = self.agent.status()
        
        table = Table(title="Agent Status", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Mode", status["mode"])
        table.add_row("Model", status["model"])
        table.add_row("Working Dir", status["workdir"])
        table.add_row("Connected", "✓" if status["connected"] else "✗ Not connected")
        table.add_row("Session ID", status["session_id"])
        table.add_row("Messages", str(status["messages"]))
        table.add_row("Actions", str(status["actions"]))
        table.add_row("State", status["state"])
        
        # Logging status
        log_enabled = "✓" if self.agent.config.log_to_file else "✗"
        table.add_row("Logging", f"{log_enabled} {self.agent.logger.log_dir}")
        
        # Git status
        git_result = self.agent.tools.get_git_status()
        if git_result.success and git_result.data:
            branch = git_result.data.get("branch", "N/A")
            dirty = "dirty" if git_result.data.get("dirty") else "clean"
            table.add_row("Git Branch", f"{branch} ({dirty})")
        
        console.print(table)
        return True
    
    def cmd_mode(self, args: str) -> bool:
        """Switch mode."""
        if not args:
            console.print(f"Current mode: [cyan]{self.agent.config.mode.value}[/cyan]")
            console.print("Usage: /mode <copilot|github-models>")
            return True
        
        mode = args.strip().lower()
        if mode in ("copilot", "github-models"):
            self.agent.set_mode(mode)
            console.print(f"[green]Switched to {mode} mode[/green]")
        else:
            console.print(f"[red]Invalid mode: {mode}[/red]")
            console.print("Available modes: copilot, github-models")
        return True
    
    def cmd_model(self, args: str) -> bool:
        """Set model."""
        if not args:
            console.print(f"Current model: [cyan]{self.agent.config.model}[/cyan]")
            console.print("Usage: /model <name>")
            return True
        
        self.agent.set_model(args.strip())
        console.print(f"[green]Model set to: {args.strip()}[/green]")
        return True
    
    def cmd_models(self, args: str) -> bool:
        """List available models."""
        try:
            models = self.agent.client.get_models()
            if models:
                console.print("[bold cyan]Available Models:[/bold cyan]")
                for m in models:
                    console.print(f"  • {m.family} (max tokens: {m.max_input_tokens})")
            else:
                console.print("[yellow]No models available or bridge not connected[/yellow]")
        except CopilotBridgeError as e:
            console.print(f"[red]Error: {e}[/red]")
        return True
    
    def cmd_system(self, args: str) -> bool:
        """Set system prompt."""
        if not args:
            if self.agent.session.system_prompt:
                console.print("[bold]Current system prompt:[/bold]")
                console.print(self.agent.session.system_prompt[:500] + "...")
            else:
                console.print("No system prompt set")
            console.print("\nUsage: /system <text> or /system @file.txt")
            return True
        
        if args.startswith("@"):
            # Load from file
            filepath = args[1:].strip()
            try:
                with open(filepath, "r") as f:
                    prompt = f.read()
                self.agent.set_system_prompt(prompt)
                console.print(f"[green]System prompt loaded from {filepath}[/green]")
            except Exception as e:
                console.print(f"[red]Error loading file: {e}[/red]")
        else:
            self.agent.set_system_prompt(args)
            console.print("[green]System prompt updated[/green]")
        return True
    
    def cmd_task(self, args: str) -> bool:
        """Start an autonomous task."""
        if not args:
            console.print("Usage: /task <description> or /task @file.txt")
            return True
        
        # Load task from file if specified
        task = args
        if args.startswith("@"):
            filepath = args[1:].strip()
            try:
                with open(filepath, "r") as f:
                    task = f.read()
            except Exception as e:
                console.print(f"[red]Error loading file: {e}[/red]")
                return True
        
        console.print(Panel(f"[bold]Starting task:[/bold]\n{task[:200]}...", title="Task"))
        
        # Run the task with progress updates
        def on_thought(data):
            if data.get("thought"):
                console.print(f"[dim]💭 {data['thought'][:100]}...[/dim]")
        
        def on_action_result(data):
            status = "✓" if data.get("success") else "✗"
            console.print(f"[cyan]{status} {data.get('action')}[/cyan]")
        
        def on_error(data):
            console.print(f"[red]Error: {data.get('error')}[/red]")
        
        self.agent.on("thought", on_thought)
        self.agent.on("action_result", on_action_result)
        self.agent.on("error", on_error)
        
        with console.status("[bold blue]Working on task...", spinner="dots"):
            result = self.agent.run_task(task)
        
        if result.summary:
            console.print(Panel(
                Markdown(result.summary),
                title="[bold green]Task Result[/bold green]"
            ))
        
        if result.error:
            console.print(f"[yellow]Note: {result.error}[/yellow]")
        
        return True
    
    def cmd_open(self, args: str) -> bool:
        """Preview a file."""
        if not args:
            console.print("Usage: /open <path>")
            return True
        
        result = self.agent.tools.read_file(args.strip(), 1, 50)
        if result.success:
            # Detect language for syntax highlighting
            ext = Path(args).suffix.lower()
            lang_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".json": "json", ".yaml": "yaml", ".yml": "yaml",
                ".md": "markdown", ".html": "html", ".css": "css",
                ".java": "java", ".rs": "rust", ".go": "go",
            }
            lang = lang_map.get(ext, "text")
            
            syntax = Syntax(result.output, lang, line_numbers=True)
            console.print(Panel(syntax, title=f"[cyan]{args}[/cyan]"))
            
            if result.data:
                console.print(f"[dim]Lines {result.data['start_line']}-{result.data['end_line']} of {result.data['total_lines']}[/dim]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")
        
        return True
    
    def cmd_search(self, args: str) -> bool:
        """Search workspace."""
        if not args:
            console.print("Usage: /search <pattern>")
            return True
        
        # Try glob search first
        result = self.agent.tools.search_files(f"**/*{args}*")
        if result.success and result.output:
            console.print("[bold]Matching files:[/bold]")
            console.print(result.output)
        
        # Also do grep search
        grep_result = self.agent.tools.grep_search(args)
        if grep_result.success and grep_result.output != "No matches found":
            console.print("\n[bold]Content matches:[/bold]")
            console.print(grep_result.output)
        
        return True
    
    def cmd_diff(self, args: str) -> bool:
        """Show pending changes."""
        result = self.agent.tools.run_command("git diff --stat", confirmed=True)
        if result.success:
            if result.output:
                console.print(Panel(result.output, title="Pending Changes"))
            else:
                console.print("[green]No uncommitted changes[/green]")
        else:
            console.print(f"[red]Error: {result.error}[/red]")
        return True
    
    def cmd_save(self, args: str) -> bool:
        """Save session."""
        if not args:
            args = f"session_{self.agent.session.id}.json"
        
        try:
            self.agent.save_session(args.strip())
            console.print(f"[green]Session saved to {args.strip()}[/green]")
        except Exception as e:
            console.print(f"[red]Error saving session: {e}[/red]")
        return True
    
    def cmd_load(self, args: str) -> bool:
        """Load session."""
        if not args:
            console.print("Usage: /load <path>")
            return True
        
        try:
            self.agent.load_session(args.strip())
            console.print(f"[green]Session loaded from {args.strip()}[/green]")
            console.print(f"Mode: {self.agent.config.mode.value}, Model: {self.agent.config.model}")
        except Exception as e:
            console.print(f"[red]Error loading session: {e}[/red]")
        return True
    
    def cmd_env(self, args: str) -> bool:
        """Detect environment."""
        result = self.agent.tools.detect_environment()
        console.print(Panel(result.output, title="Development Environment"))
        return True
    
    def cmd_lint(self, args: str) -> bool:
        """Run linter."""
        if args:
            cmd = args.strip()
        else:
            # Auto-detect linter
            if (Path(self.agent.config.workdir) / "pyproject.toml").exists():
                cmd = "ruff check . || python -m flake8 . || true"
            elif (Path(self.agent.config.workdir) / "package.json").exists():
                cmd = "npm run lint || npx eslint . || true"
            else:
                console.print("[yellow]Could not detect linter. Specify command: /lint <cmd>[/yellow]")
                return True
        
        console.print(f"[dim]Running: {cmd}[/dim]")
        with console.status("[bold blue]Running linter...", spinner="dots"):
            result = self.agent.tools.run_command(cmd, timeout=120, confirmed=True)
        
        if result.output:
            console.print(result.output)
        self.agent.session.state.last_lint_result = result.output
        return True
    
    def cmd_test(self, args: str) -> bool:
        """Run tests."""
        if args:
            cmd = args.strip()
        else:
            # Auto-detect test command
            if (Path(self.agent.config.workdir) / "pyproject.toml").exists():
                cmd = "pytest"
            elif (Path(self.agent.config.workdir) / "package.json").exists():
                cmd = "npm test"
            elif (Path(self.agent.config.workdir) / "pom.xml").exists():
                cmd = "mvn test"
            else:
                console.print("[yellow]Could not detect test runner. Specify command: /test <cmd>[/yellow]")
                return True
        
        console.print(f"[dim]Running: {cmd}[/dim]")
        with console.status("[bold blue]Running tests...", spinner="dots"):
            result = self.agent.tools.run_command(cmd, timeout=300, confirmed=True)
        
        if result.output:
            console.print(result.output)
        
        if result.success:
            console.print("[green]✓ Tests passed[/green]")
        else:
            console.print("[red]✗ Tests failed[/red]")
        
        self.agent.session.state.last_test_result = result.output
        return True
    
    def cmd_run(self, args: str) -> bool:
        """Run shell command."""
        if not args:
            console.print("Usage: /run <command>")
            return True
        
        result = self.agent.tools.run_command(args.strip())
        
        if result.data and result.data.get("needs_confirmation"):
            console.print(result.output)
            return True
        
        if result.output:
            console.print(result.output)
        
        if not result.success:
            console.print(f"[red]Command failed (exit code: {result.data.get('returncode', 'unknown')})[/red]")
        
        return True
    
    def cmd_confirm(self, args: str) -> bool:
        """Confirm pending action."""
        result = self.agent.tools.confirm_action()
        if result.success:
            console.print(f"[green]{result.output}[/green]")
        else:
            console.print(f"[yellow]{result.output or result.error}[/yellow]")
        return True
    
    def cmd_rollback(self, args: str) -> bool:
        """Rollback uncommitted changes."""
        console.print("[yellow]⚠️  This will discard all uncommitted changes.[/yellow]")
        confirm = Prompt.ask("Type 'yes' to confirm", default="no")
        
        if confirm.lower() == "yes":
            result = self.agent.tools.run_command("git checkout -- .", confirmed=True)
            if result.success:
                console.print("[green]Changes rolled back[/green]")
            else:
                console.print(f"[red]Rollback failed: {result.error}[/red]")
        else:
            console.print("[dim]Rollback cancelled[/dim]")
        
        return True
    
    def cmd_clear(self, args: str) -> bool:
        """Clear conversation history."""
        self.agent.session.clear_conversation()
        console.print("[green]Conversation cleared[/green]")
        return True
    
    def cmd_logs(self, args: str) -> bool:
        """List or view interaction logs."""
        log_dir = self.agent.logger.log_dir
        
        if not log_dir.exists():
            console.print(f"[yellow]No logs found. Log directory: {log_dir}[/yellow]")
            return True
        
        if args:
            # View specific log
            session_id = args.strip()
            log_data = self.agent.logger.load_log(session_id)
            
            if log_data:
                # Display summary
                console.print(Panel(
                    f"[bold]Task:[/bold] {log_data.get('task', 'N/A')[:200]}\n"
                    f"[bold]Status:[/bold] {log_data.get('status', 'N/A')}\n"
                    f"[bold]Started:[/bold] {log_data.get('started_at', 'N/A')}\n"
                    f"[bold]Completed:[/bold] {log_data.get('completed_at', 'N/A')}\n"
                    f"[bold]Iterations:[/bold] {len(log_data.get('iterations', []))}\n"
                    f"[bold]LLM Calls:[/bold] {len(log_data.get('llm_calls', []))}\n"
                    f"[bold]Tool Calls:[/bold] {len(log_data.get('tool_calls', []))}",
                    title=f"[cyan]Log: {session_id}[/cyan]"
                ))
                
                # Show iterations
                iterations = log_data.get('iterations', [])
                if iterations:
                    console.print("\n[bold]Iterations:[/bold]")
                    for it in iterations:
                        status = "✅" if it.get('is_complete') else "🔄"
                        console.print(f"  {status} [{it.get('iteration')}] {it.get('action', 'N/A')}")
                        if it.get('thought'):
                            console.print(f"      💭 {it['thought'][:100]}...")
                
                # Show tool calls
                tool_calls = log_data.get('tool_calls', [])
                if tool_calls:
                    console.print("\n[bold]Tool Calls:[/bold]")
                    for tc in tool_calls[-10:]:  # Last 10
                        status = "✓" if tc.get('success') else "✗"
                        duration = f"{tc.get('duration_ms', 0):.0f}ms" if tc.get('duration_ms') else ""
                        console.print(f"  {status} {tc.get('tool')}: {duration}")
                
                # Show final result
                if log_data.get('final_result'):
                    console.print(f"\n[bold]Result:[/bold]\n{log_data['final_result'][:500]}")
                if log_data.get('error'):
                    console.print(f"\n[bold red]Error:[/bold red] {log_data['error']}")
            else:
                # Try to find by partial match
                log_files = list(log_dir.glob(f"*{session_id}*_complete.json"))
                if log_files:
                    console.print(f"[yellow]Log '{session_id}' not found. Did you mean:[/yellow]")
                    for f in log_files[:5]:
                        console.print(f"  • {f.stem.replace('_complete', '')}")
                else:
                    console.print(f"[red]Log not found: {session_id}[/red]")
        else:
            # List all logs
            log_files = sorted(log_dir.glob("interaction_*_complete.json"), reverse=True)
            
            if not log_files:
                console.print(f"[yellow]No interaction logs found in {log_dir}[/yellow]")
                return True
            
            table = Table(title="Interaction Logs")
            table.add_column("Session ID", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Iterations")
            table.add_column("Date")
            
            for log_file in log_files[:20]:  # Last 20
                try:
                    with open(log_file) as f:
                        data = json.load(f)
                    
                    session_id = data.get('session_id', log_file.stem)
                    status = data.get('status', 'unknown')
                    iterations = len(data.get('iterations', []))
                    started = data.get('started_at', '')[:16]
                    
                    status_color = {
                        'completed': '[green]completed[/green]',
                        'failed': '[red]failed[/red]',
                        'incomplete': '[yellow]incomplete[/yellow]',
                    }.get(status, status)
                    
                    table.add_row(session_id, status_color, str(iterations), started)
                except:
                    pass
            
            console.print(table)
            console.print(f"\n[dim]Log directory: {log_dir}[/dim]")
            console.print("[dim]Use /logs <session_id> to view details[/dim]")
        
        return True


# ==================== Main CLI ====================

def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Developer Agent - Autonomous software development assistant",
    )
    
    parser.add_argument(
        "--mode", "-m",
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
        "--system", "-s",
        help="System prompt (or @file to load from file)",
    )
    
    parser.add_argument(
        "--workdir", "-w",
        default=str(Path.cwd()),
        help="Working directory (default: current directory)",
    )
    
    parser.add_argument(
        "--non-interactive", "-n",
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
        "--verbose", "-v",
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


def run_interactive(agent: Agent):
    """Run interactive CLI loop."""
    handler = CommandHandler(agent)
    
    # Print welcome
    console.print(Panel(
        "[bold cyan]Developer Agent[/bold cyan]\n"
        f"Mode: {agent.config.mode.value} | Model: {agent.config.model}\n"
        "Type /help for commands or just chat.",
        title="Welcome"
    ))
    
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
        print(f"\n[Log saved to: {agent.logger.log_dir}/interaction_{agent.session.id}_complete.json]", file=sys.stderr)


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Load system prompt from file if specified
    system_prompt = None
    if args.system:
        if args.system.startswith("@"):
            with open(args.system[1:], "r") as f:
                system_prompt = f.read()
        else:
            system_prompt = args.system
    
    # Create agent config with logging options
    config = AgentConfig(
        mode=AgentMode(args.mode),
        model=args.model,
        workdir=args.workdir,
        system_prompt=system_prompt,
        log_dir=args.log_dir,
        log_to_file=not args.no_log_file,
        log_to_console=args.verbose,
        verbose=args.verbose,
    )
    
    # Create agent
    agent = Agent(config)
    
    # Show log dir on startup if verbose
    if args.verbose:
        console.print(f"[dim]Log directory: {agent.logger.log_dir}[/dim]")
    
    # Run
    if args.non_interactive or args.task:
        task = " ".join(args.task) if args.task else ""
        if not task:
            console.print("[red]Error: No task provided for non-interactive mode[/red]")
            sys.exit(1)
        run_non_interactive(agent, task, args.json)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
