"""Demo: Thesis writing assistant.

This example demonstrates the complete thesis writing workflow:
1. Search and collect academic papers
2. Generate thesis outline
3. Write sections with RAG
4. Export formatted .docx document
"""

from llm_service.thesis import ThesisAgent, CitationStyle
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


def main():
    console.print(Panel.fit(
        "[bold cyan]学位论文写作助手演示[/bold cyan]\n"
        "Thesis Writing Assistant Demo",
        border_style="cyan"
    ))
    
    # Initialize agent
    console.print("\n[bold]1. Initializing thesis agent...[/bold]")
    agent = ThesisAgent(citation_style=CitationStyle.GB_T_7714)
    console.print("[green]✓ Agent initialized[/green]")
    
    # Search papers
    console.print("\n[bold]2. Searching academic papers...[/bold]")
    query = "Transformer模型在自然语言处理中的应用"
    console.print(f"Query: {query}")
    
    papers = agent.search_papers(query, limit=5, auto_add=True)
    console.print(f"[green]✓ Found {len(papers)} papers[/green]")
    
    for i, paper in enumerate(papers, 1):
        console.print(f"  {i}. {paper.title[:80]}...")
        console.print(f"     Authors: {', '.join(paper.authors[:2])}")
        console.print(f"     Year: {paper.publication_year}")
    
    # Generate outline
    console.print("\n[bold]3. Generating thesis outline...[/bold]")
    topic = "基于Transformer的中文文本分类方法研究"
    outline = agent.generate_outline(topic)
    
    console.print(f"[green]✓ Outline generated: {outline.title}[/green]")
    console.print(f"\nChapters:")
    for chapter in outline.chapters[:3]:  # Show first 3 chapters
        console.print(f"  • {chapter['number']} {chapter['title']}")
        for section in chapter.get('sections', [])[:2]:  # Show first 2 sections
            console.print(f"    - {section['number']} {section['title']}")
    
    # Write section
    console.print("\n[bold]4. Writing section with RAG...[/bold]")
    section = agent.write_section(
        section_id="1.1",
        section_title="研究背景",
        target_words=500,
        user_requirements="介绍Transformer模型的发展历程",
        use_rag=True
    )
    
    console.print(f"[green]✓ Section written ({section.word_count} words)[/green]")
    console.print(f"\n[bold]Preview:[/bold]")
    preview = section.content[:300] + "..." if len(section.content) > 300 else section.content
    console.print(Panel(Markdown(preview), title="1.1 研究背景"))
    
    if section.citations:
        console.print(f"\n[dim]Citations used: {', '.join(section.citations)}[/dim]")
    
    # Save section
    import tempfile
    import os
    
    temp_dir = tempfile.mkdtemp()
    section_file = os.path.join(temp_dir, "1.1_研究背景.md")
    agent.save_section("1.1", section_file)
    console.print(f"[green]✓ Section saved to {section_file}[/green]")
    
    # Write another section
    console.print("\n[bold]5. Writing another section...[/bold]")
    section2 = agent.write_section(
        section_id="1.2",
        section_title="研究意义",
        target_words=400,
        use_rag=True
    )
    console.print(f"[green]✓ Section 1.2 written ({section2.word_count} words)[/green]")
    
    # Generate bibliography
    console.print("\n[bold]6. Generating bibliography...[/bold]")
    references = agent.citation_manager.generate_bibliography()
    console.print(f"[green]✓ Generated {len(references)} references[/green]")
    
    if references:
        console.print(f"\n[bold]Sample references (GB/T 7714-2015):[/bold]")
        for ref in references[:2]:  # Show first 2
            console.print(f"  {ref}")
    
    # Export to .docx
    console.print("\n[bold]7. Exporting to .docx...[/bold]")
    output_file = os.path.join(temp_dir, "thesis_demo.docx")
    
    try:
        agent.export_docx(
            output_path=output_file,
            formatting_spec="标准中国高校硕士学位论文",
            include_cover=True,
            title=outline.title,
            author="张三",
            institution="示例大学",
            advisor="李教授",
            date="2026年1月"
        )
        console.print(f"[green]✓ Thesis exported to {output_file}[/green]")
        console.print(f"\n[dim]Document includes:[/dim]")
        console.print(f"  • Cover page")
        console.print(f"  • Table of contents")
        console.print(f"  • {len(agent.sections)} sections")
        console.print(f"  • {len(references)} references")
        console.print(f"\n[yellow]Note: Open the .docx file in Microsoft Word and update the table of contents[/yellow]")
    except ImportError as e:
        console.print(f"[yellow]Warning: python-docx not installed, skipping .docx export[/yellow]")
        console.print(f"[dim]Install with: pip install python-docx[/dim]")
    
    # Summary
    console.print(Panel.fit(
        f"[bold green]Demo Completed![/bold green]\n\n"
        f"Papers collected: {len(papers)}\n"
        f"Sections written: {len(agent.sections)}\n"
        f"References: {len(references)}\n"
        f"Output directory: {temp_dir}\n\n"
        f"[bold]Next steps:[/bold]\n"
        f"  • llm thesis search <query> - Search more papers\n"
        f"  • llm thesis outline <topic> - Generate outline\n"
        f"  • llm thesis write -s <id> -t <title> - Write sections\n"
        f"  • llm thesis export <output.docx> -t <title> -a <author>",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
