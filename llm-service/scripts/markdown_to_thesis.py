#!/usr/bin/env python3
"""Convert markdown file to formatted thesis .docx.

This script converts a markdown file into a properly formatted master's thesis
.docx document using LLM-based formatting interpretation.
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Optional
import argparse

from llm_service.thesis import ThesisAgent, CitationStyle
from llm_service.thesis.models import ThesisSection
from rich.console import Console

console = Console()


def parse_markdown_sections(markdown_content: str) -> List[ThesisSection]:
    """Parse markdown content into thesis sections.
    
    Args:
        markdown_content: Markdown file content
        
    Returns:
        List of thesis sections
    """
    sections = []
    
    # Split by headings
    lines = markdown_content.split('\n')
    current_section = None
    current_content = []
    
    for line in lines:
        # Check for headings (# Title, ## Title, ### Title)
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', line)
        
        if heading_match:
            # Save previous section if exists
            if current_section:
                content = '\n'.join(current_content).strip()
                if content:
                    current_section['content'] = content
                    sections.append(current_section)
            
            # Start new section
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            
            # Try to extract section number from title
            number_match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', title)
            if number_match:
                section_id = number_match.group(1)
                section_title = number_match.group(2)
            else:
                # Generate section ID based on position
                section_id = str(len(sections) + 1)
                section_title = title
            
            current_section = {
                'section_id': section_id,
                'title': section_title,
                'level': level
            }
            current_content = []
        else:
            current_content.append(line)
    
    # Save last section
    if current_section:
        content = '\n'.join(current_content).strip()
        if content:
            current_section['content'] = content
            sections.append(current_section)
    
    # Convert to ThesisSection objects
    thesis_sections = []
    for sec in sections:
        thesis_section = ThesisSection(
            section_id=sec['section_id'],
            title=sec['title'],
            content=sec['content'],
            word_count=len(sec['content'])
        )
        thesis_sections.append(thesis_section)
    
    return thesis_sections


def extract_references(markdown_content: str) -> List[str]:
    """Extract references section from markdown.
    
    Args:
        markdown_content: Markdown content
        
    Returns:
        List of reference strings
    """
    references = []
    
    # Look for references section
    ref_patterns = [
        r'#{1,2}\s*参考文献',
        r'#{1,2}\s*References',
        r'#{1,2}\s*Bibliography'
    ]
    
    in_references = False
    for line in markdown_content.split('\n'):
        # Check if we're entering references section
        for pattern in ref_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                in_references = True
                break
        
        # Check if we're leaving references section (next heading)
        if in_references and re.match(r'^#{1,2}\s+', line):
            if not any(re.match(p, line, re.IGNORECASE) for p in ref_patterns):
                break
        
        # Collect reference lines
        if in_references and line.strip():
            # Skip the heading itself
            if not any(re.match(p, line, re.IGNORECASE) for p in ref_patterns):
                references.append(line.strip())
    
    return references


def main():
    parser = argparse.ArgumentParser(
        description='Convert markdown to formatted thesis .docx'
    )
    parser.add_argument(
        'input',
        type=str,
        help='Input markdown file'
    )
    parser.add_argument(
        'output',
        type=str,
        help='Output .docx file'
    )
    parser.add_argument(
        '--title',
        '-t',
        type=str,
        required=True,
        help='Thesis title (论文标题)'
    )
    parser.add_argument(
        '--author',
        '-a',
        type=str,
        required=True,
        help='Author name (作者姓名)'
    )
    parser.add_argument(
        '--format',
        '-f',
        type=str,
        default='标准中国高校硕士学位论文',
        help='Formatting specification (格式要求)'
    )
    parser.add_argument(
        '--institution',
        '-i',
        type=str,
        help='Institution name (学校名称)'
    )
    parser.add_argument(
        '--advisor',
        type=str,
        help='Advisor name (导师姓名)'
    )
    parser.add_argument(
        '--date',
        '-d',
        type=str,
        help='Date (日期)'
    )
    parser.add_argument(
        '--no-cover',
        action='store_true',
        help='Skip cover page'
    )
    parser.add_argument(
        '--citation-style',
        type=str,
        choices=['GB/T7714-2015', 'APA', 'IEEE'],
        default='GB/T7714-2015',
        help='Citation style'
    )
    
    args = parser.parse_args()
    
    # Read markdown file
    input_path = Path(args.input)
    if not input_path.exists():
        console.print(f"[red]Error: File not found: {args.input}[/red]")
        sys.exit(1)
    
    console.print(f"[bold]Reading markdown file:[/bold] {args.input}")
    markdown_content = input_path.read_text(encoding='utf-8')
    
    # Parse sections
    console.print("[bold]Parsing sections...[/bold]")
    sections = parse_markdown_sections(markdown_content)
    console.print(f"[green]✓ Found {len(sections)} sections[/green]")
    
    for sec in sections:
        console.print(f"  {sec.section_id} {sec.title} ({sec.word_count} words)")
    
    # Extract references
    console.print("[bold]Extracting references...[/bold]")
    references = extract_references(markdown_content)
    if references:
        console.print(f"[green]✓ Found {len(references)} references[/green]")
    else:
        console.print("[yellow]! No references section found[/yellow]")
        references = []
    
    # Initialize agent
    console.print("[bold]Initializing thesis agent...[/bold]")
    citation_style_map = {
        'GB/T7714-2015': CitationStyle.GB_T_7714,
        'APA': CitationStyle.APA,
        'IEEE': CitationStyle.IEEE
    }
    agent = ThesisAgent(citation_style=citation_style_map[args.citation_style])
    
    # Add sections to agent
    for section in sections:
        agent.sections[section.section_id] = section
    
    # Prepare metadata
    metadata = {}
    
    if args.institution:
        metadata['institution'] = args.institution
    if args.advisor:
        metadata['advisor'] = args.advisor
    if args.date:
        metadata['date'] = args.date
    
    # Generate .docx
    console.print(f"[bold]Generating .docx with format:[/bold] {args.format}")
    
    with console.status("[bold blue]Creating document...", spinner="dots"):
        from llm_service.thesis.docx_generator import create_thesis_document
        
        output_path = create_thesis_document(
            sections=sections,
            references=references,
            formatting_spec=args.format,
            title=args.title,
            author=args.author,
            output_path=args.output,
            **metadata
        )
    
    console.print(f"[bold green]✓ Thesis document created:[/bold green] {output_path}")
    console.print(f"\n[dim]Summary:[/dim]")
    console.print(f"  Sections: {len(sections)}")
    console.print(f"  References: {len(references)}")
    console.print(f"  Total words: {sum(s.word_count for s in sections)}")
    console.print(f"\n[yellow]Note: Open the .docx in Word and update the table of contents (right-click → Update Field)[/yellow]")


if __name__ == '__main__':
    main()
