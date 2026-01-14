"""Command-line interface for LLM Service."""

import sys
import json
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from .client import LLMClient, Message, MessageRole, APIError
from .config import Config
from .auth import AuthenticationError


console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """LLM Service - Command-line LLM client using GitHub Copilot."""
    pass


@main.command()
@click.argument("prompt", nargs=-1, required=False)
@click.option("--system", "-s", help="System prompt")
@click.option("--model", "-m", help="Model to use")
@click.option("--temperature", "-t", type=float, help="Temperature (0.0-2.0)")
@click.option("--max-tokens", type=int, help="Maximum tokens in response")
@click.option("--markdown/--no-markdown", default=True, help="Render as markdown")
@click.option("--json-output", is_flag=True, help="Output as JSON")
def query(
    prompt: tuple,
    system: Optional[str],
    model: Optional[str],
    temperature: Optional[float],
    max_tokens: Optional[int],
    markdown: bool,
    json_output: bool,
):
    """Send a single query to the LLM.
    
    Examples:
        llm query "What is Python?"
        llm query "Explain async/await" --system "You are a Python expert"
        echo "What is Rust?" | llm query
    """
    # Get prompt from args or stdin
    if prompt:
        prompt_text = " ".join(prompt)
    elif not sys.stdin.isatty():
        prompt_text = sys.stdin.read().strip()
    else:
        console.print("[red]Error: No prompt provided[/red]")
        sys.exit(1)
    
    if not prompt_text:
        console.print("[red]Error: Empty prompt[/red]")
        sys.exit(1)
    
    try:
        # Initialize client
        client = LLMClient()
        
        # Build kwargs
        kwargs = {}
        if model:
            kwargs["model"] = model
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        
        # Send query
        with console.status("[bold blue]Thinking...", spinner="dots"):
            response = client.simple_query(prompt_text, system_prompt=system, **kwargs)
        
        # Output response
        if json_output:
            output = {"response": response, "prompt": prompt_text}
            if system:
                output["system"] = system
            console.print_json(data=output)
        elif markdown:
            console.print(Panel(Markdown(response), title="[bold blue]Response[/bold blue]"))
        else:
            console.print(response)
    
    except (ValueError, AuthenticationError) as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
        console.print("\n[yellow]Make sure GITHUB_TOKEN is set:[/yellow]")
        console.print("  export GITHUB_TOKEN='your_token_here'")
        sys.exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(0)


@main.command()
@click.option("--system", "-s", help="System prompt for conversation")
@click.option("--model", "-m", help="Model to use")
@click.option("--save", type=click.Path(), help="Save conversation to file")
@click.option("--load", type=click.Path(exists=True), help="Load conversation from file")
def chat(
    system: Optional[str],
    model: Optional[str],
    save: Optional[str],
    load: Optional[str],
):
    """Start an interactive chat session.
    
    Examples:
        llm chat
        llm chat --system "You are a helpful coding assistant"
        llm chat --load conversation.json --save conversation.json
    """
    try:
        # Initialize client
        client = LLMClient()
        
        # Load or create conversation
        conversation: List[Message] = []
        
        if load:
            try:
                with open(load, "r") as f:
                    data = json.load(f)
                    conversation = [Message(**msg) for msg in data.get("messages", [])]
                console.print(f"[green]Loaded conversation from {load}[/green]")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not load conversation: {e}[/yellow]")
        
        if system and not any(msg.role == MessageRole.SYSTEM for msg in conversation):
            conversation.insert(0, Message(role=MessageRole.SYSTEM, content=system))
        
        # Display welcome
        console.print(Panel(
            "[bold blue]LLM Chat Session[/bold blue]\n"
            "Type your messages and press Enter.\n"
            "Commands: /quit, /save, /clear, /help",
            title="Welcome"
        ))
        
        # Build kwargs
        kwargs = {}
        if model:
            kwargs["model"] = model
        
        # Chat loop
        while True:
            try:
                # Get user input
                user_input = Prompt.ask("\n[bold green]You[/bold green]")
                
                if not user_input.strip():
                    continue
                
                # Handle commands
                if user_input.startswith("/"):
                    if user_input == "/quit" or user_input == "/exit":
                        break
                    elif user_input == "/clear":
                        conversation = []
                        if system:
                            conversation.append(Message(role=MessageRole.SYSTEM, content=system))
                        console.print("[yellow]Conversation cleared[/yellow]")
                        continue
                    elif user_input.startswith("/save"):
                        parts = user_input.split(maxsplit=1)
                        save_path = parts[1] if len(parts) > 1 else save or "conversation.json"
                        _save_conversation(conversation, save_path)
                        continue
                    elif user_input == "/help":
                        console.print(Panel(
                            "/quit - Exit chat\n"
                            "/clear - Clear conversation history\n"
                            "/save [path] - Save conversation\n"
                            "/help - Show this help",
                            title="Commands"
                        ))
                        continue
                    else:
                        console.print(f"[red]Unknown command: {user_input}[/red]")
                        continue
                
                # Get response
                with console.status("[bold blue]Thinking...", spinner="dots"):
                    response_text, conversation = client.continue_conversation(
                        conversation, user_input, **kwargs
                    )
                
                # Display response
                console.print("\n[bold blue]Assistant[/bold blue]")
                console.print(Markdown(response_text))
                
            except KeyboardInterrupt:
                console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
        
        # Auto-save if specified
        if save:
            _save_conversation(conversation, save)
        
        console.print("\n[blue]Goodbye![/blue]")
    
    except (ValueError, AuthenticationError) as e:
        console.print(f"[red]Configuration Error:[/red] {e}")
        console.print("\n[yellow]Make sure GITHUB_TOKEN is set:[/yellow]")
        console.print("  export GITHUB_TOKEN='your_token_here'")
        sys.exit(1)
    except APIError as e:
        console.print(f"[red]API Error:[/red] {e}")
        sys.exit(1)


def _save_conversation(conversation: List[Message], path: str):
    """Save conversation to file."""
    try:
        data = {
            "messages": [msg.model_dump() for msg in conversation]
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]Conversation saved to {path}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to save conversation: {e}[/red]")


@main.command()
def config():
    """Show current configuration."""
    try:
        cfg = Config.from_env()
        
        # Mask token
        token = cfg.github_token
        if token:
            token = token[:8] + "..." + token[-4:] if len(token) > 12 else "***"
        else:
            token = "[red]Not set[/red]"
        
        console.print(Panel(
            f"[bold]GitHub Token:[/bold] {token}\n"
            f"[bold]API Base URL:[/bold] {cfg.api_base_url}\n"
            f"[bold]Model:[/bold] {cfg.model}\n"
            f"[bold]Max Tokens:[/bold] {cfg.max_tokens}\n"
            f"[bold]Temperature:[/bold] {cfg.temperature}\n"
            f"[bold]Timeout:[/bold] {cfg.timeout}s",
            title="Configuration"
        ))
        
        # Show config directory
        config_dir = cfg.get_config_dir()
        console.print(f"\n[dim]Config directory: {config_dir}[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        sys.exit(1)


@main.command()
def test():
    """Test API connection and authentication."""
    console.print(Panel(
        "[bold blue]Testing LLM Service Connection[/bold blue]",
        title="Test"
    ))
    
    try:
        # Load config
        cfg = Config.from_env()
        
        if not cfg.validate_auth():
            console.print("[red]✗ No GitHub token configured[/red]")
            console.print("\nRun: [yellow]llm setup[/yellow]")
            sys.exit(1)
        
        console.print("[green]✓ GitHub token found[/green]")
        
        # Test authentication
        console.print("\n[bold]Testing authentication...[/bold]")
        from .auth import GitHubAuthenticator
        
        auth = GitHubAuthenticator(cfg.github_token)
        
        try:
            with console.status("Getting Copilot token...", spinner="dots"):
                token = auth.get_copilot_token()
            console.print("[green]✓ Authentication successful[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Direct token fetch failed: {e}[/yellow]")
            console.print("[dim]Will use GitHub token directly[/dim]")
        
        # Test API call
        console.print("\n[bold]Testing API call...[/bold]")
        
        try:
            client = LLMClient(cfg)
            
            with console.status("Sending test query...", spinner="dots"):
                response = client.simple_query(
                    "Say 'Hello' in one word",
                    max_tokens=10
                )
            
            console.print("[green]✓ API call successful![/green]")
            console.print(f"\n[dim]Response: {response[:100]}[/dim]")
            
            console.print("\n[bold green]All tests passed! ✓[/bold green]")
            console.print("\nYou can now use:")
            console.print("  [cyan]llm query 'your question'[/cyan]")
            console.print("  [cyan]llm chat[/cyan]")
            
        except APIError as e:
            console.print(f"[red]✗ API call failed: {e}[/red]")
            console.print("\n[yellow]Troubleshooting:[/yellow]")
            console.print("1. Check your GitHub Copilot subscription status")
            console.print("2. Verify your token has correct permissions")
            console.print("3. Try regenerating your GitHub token")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[red]✗ Test failed: {e}[/red]")
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


@main.command()
def setup():
    """Interactive setup wizard."""
    console.print(Panel(
        "[bold blue]LLM Service Setup[/bold blue]\n"
        "Let's configure your GitHub Copilot access.",
        title="Welcome"
    ))
    
    # Get GitHub token
    console.print("\n[bold]1. GitHub Token[/bold]")
    console.print("You need a GitHub personal access token with Copilot access.")
    console.print("Get one at: https://github.com/settings/tokens\n")
    
    token = Prompt.ask("Enter your GitHub token", password=True)
    
    if not token:
        console.print("[red]Token required. Setup cancelled.[/red]")
        return
    
    # Create config directory
    config_dir = Path.home() / ".llm-service"
    config_dir.mkdir(exist_ok=True)
    
    # Save to .env file
    env_file = config_dir / ".env"
    with open(env_file, "w") as f:
        f.write(f"GITHUB_TOKEN={token}\n")
    
    console.print(f"\n[green]✓ Configuration saved to {env_file}[/green]")
    
    # Test connection
    console.print("\n[bold]2. Testing connection...[/bold]")
    
    try:
        client = LLMClient(Config(github_token=token))
        with console.status("Sending test query...", spinner="dots"):
            response = client.simple_query("Say 'Hello!'", max_tokens=50)
        
        console.print("[green]✓ Connection successful![/green]")
        console.print(f"\n[dim]Test response: {response[:100]}...[/dim]")
        
        console.print("\n[bold green]Setup complete![/bold green]")
        console.print("\nTry it out:")
        console.print("  llm query 'What is Python?'")
        console.print("  llm chat")
        
    except Exception as e:
        console.print(f"[red]✗ Connection failed: {e}[/red]")
        console.print("\nPlease check your token and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
