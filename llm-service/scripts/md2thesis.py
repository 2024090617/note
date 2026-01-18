#!/usr/bin/env python3
"""Quick markdown to thesis converter - interactive version."""

from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
import sys
import os

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_service.thesis import ThesisAgent, CitationStyle
from llm_service.thesis.models import ThesisSection
import re

console = Console()


def parse_markdown_sections(content: str):
    """Simple markdown parser."""
    sections = []
    lines = content.split('\n')
    current_section = None
    current_content = []
    
    for line in lines:
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', line)
        
        if heading_match:
            if current_section:
                content_text = '\n'.join(current_content).strip()
                if content_text:
                    current_section['content'] = content_text
                    sections.append(current_section)
            
            title = heading_match.group(2).strip()
            number_match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', title)
            
            if number_match:
                section_id = number_match.group(1)
                section_title = number_match.group(2)
            else:
                section_id = str(len(sections) + 1)
                section_title = title
            
            current_section = {'section_id': section_id, 'title': section_title}
            current_content = []
        else:
            current_content.append(line)
    
    if current_section and current_content:
        current_section['content'] = '\n'.join(current_content).strip()
        sections.append(current_section)
    
    return [ThesisSection(
        section_id=s['section_id'],
        title=s['title'],
        content=s['content'],
        word_count=len(s['content'])
    ) for s in sections]


def main():
    console.print("[bold cyan]Markdown to Thesis Converter[/bold cyan]\n")
    
    # Get input file
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = Prompt.ask("Enter markdown file path")
    
    input_path = Path(input_file)
    if not input_path.exists():
        console.print(f"[red]Error: File not found: {input_file}[/red]")
        sys.exit(1)
    
    # Read file
    console.print(f"\n[bold]Reading:[/bold] {input_path.name}")
    content = input_path.read_text(encoding='utf-8')
    
    # Parse sections
    sections = parse_markdown_sections(content)
    console.print(f"[green]✓ Found {len(sections)} sections[/green]")
    
    for i, sec in enumerate(sections[:5], 1):
        console.print(f"  {sec.section_id} {sec.title} ({sec.word_count} chars)")
    if len(sections) > 5:
        console.print(f"  ... and {len(sections) - 5} more")
    
    # Get metadata
    console.print("\n[bold]Thesis Information:[/bold]")
    title = Prompt.ask("Thesis title (论文标题)", default=input_path.stem)
    author = Prompt.ask("Author (作者)")
    institution = Prompt.ask("Institution (学校)", default="")
    advisor = Prompt.ask("Advisor (导师)", default="")
    
    # Formatting
    console.print("\n[bold]Formatting Options:[/bold]")
    console.print("1. 标准中国高校硕士学位论文")
    console.print("2. 标准中国高校博士学位论文")
    console.print("3. Custom specification")
    
    format_choice = Prompt.ask("Choose format", choices=["1", "2", "3"], default="1")
    
    if format_choice == "1":
        format_spec = "标准中国高校硕士学位论文"
    elif format_choice == "2":
        format_spec = "标准中国高校博士学位论文"
    else:
        format_spec = Prompt.ask("Enter custom format specification")
    
    # Output file
    default_output = input_path.with_suffix('.docx')
    output_file = Prompt.ask("Output file", default=str(default_output))
    
    # Generate
    console.print(f"\n[bold]Generating .docx...[/bold]")
    
    try:
        from llm_service.thesis.docx_generator import create_thesis_document
        
        with console.status("[bold blue]Creating document...", spinner="dots"):
            metadata = {}
            if institution:
                metadata['institution'] = institution
            if advisor:
                metadata['advisor'] = advisor
            
            output_path = create_thesis_document(
                sections=sections,
                references=[],
                formatting_spec=format_spec,
                title=title,
                author=author,
                output_path=output_file,
                **metadata
            )
        
        console.print(f"\n[bold green]✓ Success![/bold green]")
        console.print(f"Created: {output_path}")
        console.print(f"Sections: {len(sections)}")
        console.print(f"Total characters: {sum(s.word_count for s in sections):,}")
        
        console.print("\n[yellow]Next steps:[/yellow]")
        console.print("1. Open the .docx file in Microsoft Word")
        console.print("2. Right-click on '目录' and select 'Update Field'")
        console.print("3. Review and adjust formatting as needed")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
