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


# ============================================================================
# Thesis Commands
# ============================================================================

@main.group()
def thesis():
    """Thesis writing assistant commands (学位论文写作助手)."""
    pass


@thesis.command()
@click.argument("query")
@click.option("--sources", "-s", multiple=True, default=["arxiv", "semantic_scholar"], 
              help="Sources to search (arxiv, semantic_scholar)")
@click.option("--limit", "-l", type=int, default=10, help="Maximum papers per source")
@click.option("--no-auto-add", is_flag=True, help="Don't automatically add to knowledge base")
def search(query: str, sources: tuple, limit: int, no_auto_add: bool):
    """Search for academic papers (搜索学术论文).
    
    Examples:
        llm thesis search "深度学习在自然语言处理中的应用"
        llm thesis search "Transformer models" --sources arxiv --limit 20
    """
    from .thesis.agent import ThesisAgent
    
    try:
        with console.status("[bold blue]Searching papers...", spinner="dots"):
            agent = ThesisAgent()
            papers = agent.search_papers(
                query=query,
                sources=list(sources),
                limit=limit,
                auto_add=not no_auto_add
            )
        
        if not papers:
            console.print("[yellow]No papers found[/yellow]")
            console.print("\n[dim]Tips:[/dim]")
            console.print("  • Try using English keywords instead of Chinese")
            console.print("  • Use simpler, more general terms")
            console.print("  • Try --sources arxiv to avoid rate limits")
            console.print("\nExample: [cyan]llm thesis search \"AI programming developer mental health\" --sources arxiv[/cyan]")
            return
        
        console.print(f"\n[bold green]Found {len(papers)} papers:[/bold green]\n")
        
        for i, paper in enumerate(papers, 1):
            console.print(f"[bold]{i}. {paper.title}[/bold]")
            console.print(f"   Authors: {', '.join(paper.authors[:3])}")
            if len(paper.authors) > 3:
                console.print(f"   ... and {len(paper.authors) - 3} more")
            console.print(f"   Year: {paper.publication_year}")
            if paper.publication_venue:
                console.print(f"   Venue: {paper.publication_venue}")
            if paper.citation_count:
                console.print(f"   Citations: {paper.citation_count}")
            if paper.arxiv_id:
                console.print(f"   ArXiv: {paper.arxiv_id}")
            if paper.doi:
                console.print(f"   DOI: {paper.doi}")
            console.print()
        
        if not no_auto_add:
            console.print(f"[green]✓ Added {len(papers)} papers to knowledge base[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@thesis.command()
@click.option("--tags", "-t", multiple=True, help="Filter by tags")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
@click.option("--sort", type=click.Choice(["year", "citations", "title"]), default="year")
def list_papers(tags: tuple, limit: int, sort: str):
    """List papers in knowledge base (列出知识库中的论文)."""
    from .thesis.agent import ThesisAgent
    
    try:
        agent = ThesisAgent()
        papers = agent.list_papers(tags=list(tags) if tags else None, limit=limit)
        
        if not papers:
            console.print("[yellow]No papers found in knowledge base[/yellow]")
            return
        
        console.print(f"\n[bold green]Papers in knowledge base ({len(papers)}):[/bold green]\n")
        
        for i, paper in enumerate(papers, 1):
            title = paper.get("title", "Unknown")
            metadata = paper.get("metadata", {})
            
            console.print(f"[bold]{i}. {title}[/bold]")
            if metadata.get("authors"):
                console.print(f"   Authors: {', '.join(metadata['authors'][:3])}")
            if metadata.get("publication_year"):
                console.print(f"   Year: {metadata['publication_year']}")
            if metadata.get("citation_count"):
                console.print(f"   Citations: {metadata['citation_count']}")
            console.print()
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@thesis.command()
@click.argument("topic")
@click.option("--requirements", "-r", help="Additional requirements")
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def outline(topic: str, requirements: Optional[str], output: Optional[str]):
    """Generate thesis outline (生成论文大纲).
    
    Examples:
        llm thesis outline "基于Transformer的文本分类研究"
        llm thesis outline "Deep Learning for NLP" -o outline.json
    """
    from .thesis.agent import ThesisAgent
    
    try:
        with console.status("[bold blue]Generating outline...", spinner="dots"):
            agent = ThesisAgent()
            outline_obj = agent.generate_outline(topic, requirements)
        
        console.print(f"\n[bold green]Thesis Outline:[/bold green]")
        console.print(f"[bold]{outline_obj.title}[/bold]\n")
        
        for chapter in outline_obj.chapters:
            console.print(f"[bold cyan]{chapter['number']} {chapter['title']}[/bold cyan]")
            for section in chapter.get("sections", []):
                console.print(f"  {section['number']} {section['title']}")
            console.print()
        
        # Save to file if specified
        if output:
            output_path = Path(output)
            output_data = {
                "title": outline_obj.title,
                "chapters": outline_obj.chapters,
                "total_chapters": outline_obj.total_chapters,
                "generated_at": outline_obj.generated_at if hasattr(outline_obj, 'generated_at') else None
            }
            output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
            console.print(f"[green]✓ Outline saved to {output}[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@thesis.command()
@click.option("--section", "-s", required=True, help="Section ID (e.g., 1.1, 2.3)")
@click.option("--title", "-t", required=True, help="Section title")
@click.option("--words", "-w", type=int, default=800, help="Target word count")
@click.option("--requirements", "-r", help="Additional requirements")
@click.option("--output", "-o", type=click.Path(), help="Output markdown file")
@click.option("--no-rag", is_flag=True, help="Don't use knowledge base (RAG)")
def write(section: str, title: str, words: int, requirements: Optional[str], 
          output: Optional[str], no_rag: bool):
    """Write a thesis section (撰写论文章节).
    
    Examples:
        llm thesis write -s 1.1 -t "研究背景" -o sections/1.1.md
        llm thesis write -s 2.1 -t "相关工作" -w 1200 -r "重点介绍Transformer"
    """
    from .thesis.agent import ThesisAgent
    
    try:
        with console.status(f"[bold blue]Writing section {section}...", spinner="dots"):
            agent = ThesisAgent()
            section_obj = agent.write_section(
                section_id=section,
                section_title=title,
                target_words=words,
                user_requirements=requirements,
                use_rag=not no_rag
            )
        
        console.print(f"\n[bold green]Section {section}: {title}[/bold green]\n")
        console.print(Panel(Markdown(section_obj.content)))
        
        console.print(f"\n[dim]Word count: {section_obj.word_count}[/dim]")
        if section_obj.citations:
            console.print(f"[dim]Citations: {', '.join(section_obj.citations)}[/dim]")
        
        # Save to file if specified
        if output:
            agent.save_section(section, output)
            console.print(f"\n[green]✓ Section saved to {output}[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@thesis.command()
@click.argument("output", type=click.Path())
@click.option("--format", "-f", default="标准中国高校硕士学位论文", 
              help="Formatting specification")
@click.option("--title", "-t", required=True, help="Thesis title")
@click.option("--author", "-a", required=True, help="Author name")
@click.option("--institution", "-i", help="Institution name")
@click.option("--advisor", help="Advisor name")
@click.option("--date", "-d", help="Date")
@click.option("--no-cover", is_flag=True, help="Don't include cover page")
def export(output: str, format: str, title: str, author: str, 
           institution: Optional[str], advisor: Optional[str], 
           date: Optional[str], no_cover: bool):
    """Export thesis to .docx (导出论文为Word文档).
    
    Examples:
        llm thesis export thesis.docx -t "我的论文" -a "张三"
        llm thesis export output.docx -f "北京大学硕士学位论文格式" -t "Title" -a "Author"
    """
    from .thesis.agent import ThesisAgent
    
    try:
        agent = ThesisAgent()
        
        # Check if we have sections
        if not agent.sections:
            console.print("[yellow]No sections found. Write some sections first using 'llm thesis write'[/yellow]")
            sys.exit(1)
        
        metadata = {
            "title": title,
            "author": author,
        }
        
        if institution:
            metadata["institution"] = institution
        if advisor:
            metadata["advisor"] = advisor
        if date:
            metadata["date"] = date
        
        with console.status("[bold blue]Generating document...", spinner="dots"):
            output_path = agent.export_docx(
                output_path=output,
                formatting_spec=format,
                include_cover=not no_cover,
                **metadata
            )
        
        console.print(f"[green]✓ Thesis exported to {output_path}[/green]")
        console.print(f"\n[dim]Sections included: {len(agent.sections)}[/dim]")
        console.print(f"[dim]References: {len(agent.citation_manager.papers)}[/dim]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@thesis.command()
@click.option("--style", "-s", type=click.Choice(["GB/T7714-2015", "APA", "IEEE"]), 
              default="GB/T7714-2015", help="Citation style")
@click.option("--output", "-o", type=click.Path(), help="Output file")
def citations(style: str, output: Optional[str]):
    """Generate bibliography (生成参考文献).
    
    Examples:
        llm thesis citations
        llm thesis citations -s APA -o references.txt
    """
    from .thesis.agent import ThesisAgent
    from .thesis.models import CitationStyle
    
    try:
        # Map style string to enum
        style_map = {
            "GB/T7714-2015": CitationStyle.GB_T_7714,
            "APA": CitationStyle.APA,
            "IEEE": CitationStyle.IEEE
        }
        
        agent = ThesisAgent(citation_style=style_map[style])
        
        if not agent.citation_manager.papers:
            console.print("[yellow]No citations found[/yellow]")
            return
        
        references = agent.citation_manager.generate_bibliography()
        
        console.print(f"\n[bold green]Bibliography ({style}):[/bold green]\n")
        for ref in references:
            console.print(ref)
            console.print()
        
        if output:
            Path(output).write_text("\n\n".join(references), encoding="utf-8")
            console.print(f"[green]✓ Bibliography saved to {output}[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
