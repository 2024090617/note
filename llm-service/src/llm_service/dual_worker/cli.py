"""
Command-line interface for dual-worker framework.

Provides commands for planning, executing, and monitoring tasks.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from llm_service.dual_worker.config import DualWorkerConfig
from llm_service.dual_worker.planner import DualPlannerOrchestrator
from llm_service.dual_worker.orchestrator import DualWorkerOrchestrator
from llm_service.dual_worker.storage import create_state_store
from llm_service.dual_worker.debug_logger import DebugMarkdownLogger, set_debug_logger
from llm_service.dual_worker.models import (
    TaskStatus,
    ExecutionResult,
    TaskGraph,
)

console = Console()


def run_async(coro):
    """Helper to run async functions in Click commands"""
    return asyncio.run(coro)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Dual-Worker+Judge AI Framework - High-quality task execution"""
    pass


@cli.command()
@click.argument("goal")
@click.option("--output", "-o", type=click.Path(), help="Save plan to file")
@click.option("--execute", "-e", is_flag=True, help="Execute plan after creation")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--copilot", is_flag=True, help="Use Copilot Bridge for premium models (GPT-5, Claude Opus)")
def plan(goal: str, output: Optional[str], execute: bool, debug: bool, copilot: bool):
    """
    Create a task decomposition plan using dual planners.
    
    Example:
        dw plan "Build a login feature with JWT authentication"
        dw plan "Build something" --copilot  # Use GPT-5, Claude Opus via Copilot
    """
    import logging
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Initialize debug logger if --debug is enabled
    debug_logger = None
    if debug:
        session_id = str(uuid.uuid4())[:8]
        debug_logger = DebugMarkdownLogger(session_id)
        set_debug_logger(debug_logger)
        console.print(f"[dim]Debug logging enabled. Session: {session_id}[/dim]")
    
    async def create_plan():
        # Always use Copilot Bridge (default mode)
        config = DualWorkerConfig.create_copilot_bridge()
        console.print("[green]Using Copilot Bridge (GPT-5, Claude Opus 4.5)[/green]")
        planner = DualPlannerOrchestrator(config)
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_progress = progress.add_task("Creating plan with dual planners...", total=None)
            
            try:
                task_graph, metadata = await planner.create_validated_plan(goal)
                progress.update(task_progress, completed=True)
            except Exception as e:
                console.print(f"[red]✗[/red] Planning failed: {str(e)}")
                if debug_logger:
                    debug_logger.finalize(summary=f"Planning failed: {str(e)}")
                    console.print(f"\n[dim]Debug log saved to: {debug_logger.get_log_path()}[/dim]")
                sys.exit(1)
        
        # Finalize debug log if enabled
        if debug_logger:
            debug_logger.finalize(summary=f"Plan created with {len(task_graph.tasks)} tasks")
            console.print(f"\n[cyan]📝 Debug log saved to:[/cyan] {debug_logger.get_log_path()}\n")
        
        # Display plan
        console.print("\n[green]✓[/green] Plan created successfully!\n")
        
        console.print(Panel(f"[bold]{goal}[/bold]", title="Goal"))
        
        # Show metadata
        console.print(f"\n[bold]Decision:[/bold] {metadata.get('verdict', 'N/A')}")
        if "plan_a_score" in metadata:
            console.print(f"[bold]Plan A Score:[/bold] {metadata['plan_a_score']:.1f}%")
        if "plan_b_score" in metadata:
            console.print(f"[bold]Plan B Score:[/bold] {metadata['plan_b_score']:.1f}%")
        
        # Task table
        table = Table(title=f"\nTask Plan ({len(task_graph.tasks)} tasks)")
        table.add_column("ID", style="cyan")
        table.add_column("Description")
        table.add_column("Dependencies", style="dim")
        table.add_column("Criticality", style="yellow")
        
        for task in task_graph.tasks:
            deps = ", ".join(task.dependencies) if task.dependencies else "-"
            table.add_row(
                task.id,
                task.description[:60] + "..." if len(task.description) > 60 else task.description,
                deps,
                task.criticality.value,
            )
        
        console.print(table)
        
        # Save if requested
        if output:
            store = create_state_store()
            filepath = store.save_task_graph(task_graph, goal, metadata)
            console.print(f"\n[green]Plan saved to:[/green] {filepath}")
        
        # Execute if requested
        if execute:
            console.print("\n[bold]Executing plan...[/bold]\n")
            session_id = str(uuid.uuid4())[:8]
            await execute_plan_interactive(task_graph, goal, session_id, config)
        else:
            # Ask if user wants to execute
            if Confirm.ask("\nExecute this plan now?"):
                session_id = str(uuid.uuid4())[:8]
                await execute_plan_interactive(task_graph, goal, session_id, config)
    
    run_async(create_plan())


async def execute_plan_interactive(
    task_graph: TaskGraph,
    goal: str,
    session_id: str,
    config: DualWorkerConfig,
):
    """Execute plan with interactive progress"""
    
    orchestrator = DualWorkerOrchestrator(config)
    store = create_state_store()
    
    results = {}
    
    async def progress_callback(task_id: str, result: ExecutionResult):
        """Called after each task completes"""
        status_emoji = {
            TaskStatus.COMPLETED: "[green]✓[/green]",
            TaskStatus.FAILED: "[red]✗[/red]",
            TaskStatus.ESCALATED: "[yellow]⚠[/yellow]",
            TaskStatus.REJECTED: "[red]🚫[/red]",
        }
        
        emoji = status_emoji.get(result.status, "❓")
        console.print(f"{emoji} Task {task_id}: {result.status.value} ({result.total_time_seconds:.1f}s)")
        
        # Save result
        store.save_execution_result(result, session_id)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task_progress = progress.add_task(
            f"Executing {len(task_graph.tasks)} tasks...",
            total=len(task_graph.tasks)
        )
        
        try:
            results = await orchestrator.execute_graph(
                task_graph,
                progress_callback=progress_callback,
            )
        except Exception as e:
            console.print(f"\n[red]Execution failed:[/red] {str(e)}")
            sys.exit(1)
    
    # Summary
    console.print("\n[bold]Execution Summary[/bold]\n")
    
    completed = sum(1 for r in results.values() if r.status == TaskStatus.COMPLETED)
    failed = sum(1 for r in results.values() if r.status == TaskStatus.FAILED)
    escalated = sum(1 for r in results.values() if r.status == TaskStatus.ESCALATED)
    
    console.print(f"✅ Completed: {completed}")
    console.print(f"❌ Failed: {failed}")
    console.print(f"⚠️  Escalated: {escalated}")
    
    # Save summary
    result_list = list(results.values())
    summary_path = store.create_session_summary(session_id, result_list, task_graph, goal)
    console.print(f"\n[green]Summary saved to:[/green] {summary_path}")
    
    # Export markdown
    md_path = store.export_to_markdown(session_id, result_list, task_graph, goal)
    console.print(f"[green]Report exported to:[/green] {md_path}")


@cli.command()
@click.argument("plan_file", type=click.Path(exists=True))
@click.option("--session-id", "-s", help="Session identifier")
@click.option("--debug", is_flag=True, help="Enable debug logging")
def execute(plan_file: str, session_id: Optional[str], debug: bool):
    """
    Execute a saved task plan.
    
    Example:
        dw execute ~/.dual_worker_state/plans/plan_20260119_120000.json
    """
    import logging
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    async def run_execution():
        # Load plan
        store = create_state_store()
        task_graph, goal, metadata = store.load_task_graph(Path(plan_file))
        
        console.print(Panel(f"[bold]{goal}[/bold]", title="Goal"))
        console.print(f"\nLoaded plan with {len(task_graph.tasks)} tasks\n")
        
        # Execute with Copilot Bridge (default mode)
        config = DualWorkerConfig.create_copilot_bridge()
        console.print("[green]Using Copilot Bridge (GPT-5, Claude Opus 4.5)[/green]")
        sid = session_id or str(uuid.uuid4())[:8]
        
        await execute_plan_interactive(task_graph, goal, sid, config)
    
    run_async(run_execution())


@cli.command()
@click.option("--limit", "-n", default=10, type=int, help="Number of results to show")
def history(limit: int):
    """
    Show execution history.
    
    Example:
        dw history -n 20
    """
    store = create_state_store()
    
    execution_files = store.list_executions(limit=limit)
    
    if not execution_files:
        console.print("[yellow]No execution history found[/yellow]")
        return
    
    table = Table(title=f"Recent Executions (last {limit})")
    table.add_column("Task ID", style="cyan")
    table.add_column("Status")
    table.add_column("Time", style="dim")
    table.add_column("Model", style="green")
    
    for filepath in execution_files:
        try:
            result_data = store.load_execution_result(filepath)
            
            status_emoji = {
                "completed": "✅",
                "failed": "❌",
                "escalated": "⚠️",
                "rejected": "🚫",
            }.get(result_data.get("status", ""), "❓")
            
            table.add_row(
                result_data.get("task_id", "N/A"),
                f"{status_emoji} {result_data.get('status', 'N/A')}",
                f"{result_data.get('total_time_seconds', 0):.1f}s",
                result_data.get("final_metadata", {}).get("judge_model", "N/A")[:20],
            )
        except Exception as e:
            console.print(f"[red]Error loading {filepath.name}:[/red] {str(e)}")
    
    console.print(table)


@cli.command()
@click.option("--limit", "-n", default=10, type=int, help="Number of plans to show")
def plans(limit: int):
    """
    List saved plans.
    
    Example:
        dw plans -n 5
    """
    store = create_state_store()
    
    plan_files = store.list_plans(limit=limit)
    
    if not plan_files:
        console.print("[yellow]No saved plans found[/yellow]")
        return
    
    table = Table(title=f"Saved Plans (last {limit})")
    table.add_column("File", style="cyan")
    table.add_column("Tasks", style="green")
    table.add_column("Created", style="dim")
    
    for filepath in plan_files:
        try:
            task_graph, goal, metadata = store.load_task_graph(filepath)
            
            table.add_row(
                filepath.name,
                str(len(task_graph.tasks)),
                filepath.stat().st_mtime,
            )
        except Exception as e:
            console.print(f"[red]Error loading {filepath.name}:[/red] {str(e)}")
    
    console.print(table)


@cli.command()
def config():
    """
    Show current configuration.
    
    Example:
        dw config
    """
    try:
        # Show Copilot Bridge configuration (default mode)
        cfg = DualWorkerConfig.create_copilot_bridge()
        
        console.print("[bold]Dual-Worker Configuration[/bold]\n")
        console.print("[green]Mode: Copilot Bridge (GPT-5, Claude Opus 4.5)[/green]\n")
        
        # Model assignments
        table = Table(title="Model Assignments")
        table.add_column("Role", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("Rate Limit", style="yellow")
        
        for role, model_cfg in cfg.models.items():
            table.add_row(
                role.value,
                model_cfg.model_name,
                model_cfg.rate_limit or "Unknown",
            )
        
        console.print(table)
        
        # Settings
        console.print("\n[bold]Settings[/bold]")
        console.print(f"Max Retries: {cfg.max_retries}")
        console.print(f"Auto Escalate Threshold: {cfg.auto_escalate_threshold}")
        console.print(f"Rejection Threshold: {cfg.rejection_threshold}")
        console.print(f"Parallel Workers: {cfg.enable_parallel_workers}")
        console.print(f"Auto Retry: {cfg.enable_auto_retry}")
        
    except Exception as e:
        console.print(f"[red]Failed to load configuration:[/red] {str(e)}")
        sys.exit(1)


@cli.command()
@click.argument("goal")
@click.option("--criticality", "-c", type=click.Choice(["simple", "standard", "important", "critical"]), default="standard")
@click.option("--task-type", "-t", type=click.Choice(["code", "writing", "analysis", "planning", "qa", "translation", "creative", "review", "general"]), default="general", help="Task type for specialized prompts")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--copilot", is_flag=True, help="Use Copilot Bridge for premium models (GPT-5, Claude Opus)")
def quick(goal: str, criticality: str, task_type: str, debug: bool, copilot: bool):
    """
    Quick single-task execution (no planning).
    
    Example:
        dw quick "Write a function to validate email addresses" -c important
        dw quick "Write a project status report" -t writing -c standard
        dw quick "Analyze the Q4 sales data" -t analysis
        dw quick "Create a roadmap for v2.0 release" -t planning
        dw quick "Translate this document to Chinese" -t translation
        dw quick "Complex task" --copilot  # Use GPT-5, Claude Opus via Copilot
    """
    import logging
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Initialize debug logger if --debug is enabled
    debug_logger = None
    if debug:
        session_id = str(uuid.uuid4())[:8]
        debug_logger = DebugMarkdownLogger(session_id)
        set_debug_logger(debug_logger)
        console.print(f"[dim]Debug logging enabled. Session: {session_id}[/dim]")
    
    from llm_service.dual_worker.models import TaskSchema, TaskCriticality, TaskType
    
    async def quick_execute():
        # Always use Copilot Bridge (default mode)
        config = DualWorkerConfig.create_copilot_bridge()
        console.print("[green]Using Copilot Bridge (GPT-5, Claude Opus 4.5)[/green]")
        console.print(f"[dim]Task type: {task_type}[/dim]")
        orchestrator = DualWorkerOrchestrator(config)
        
        # Create single task with task type
        task = TaskSchema(
            task_id="Q1",
            description=goal,
            input={},
            output="Implementation that fulfills the goal",
            verification="Automated verification",
            criticality=TaskCriticality(criticality),
            task_type=TaskType(task_type),
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_progress = progress.add_task("Executing task...", total=None)
            
            result = await orchestrator.execute_with_retry(task)
            progress.update(task_progress, completed=True)
        
        # Finalize debug log if enabled
        if debug_logger:
            debug_logger.finalize(summary=f"Task execution {result.status.value}")
            console.print(f"\n[cyan]📝 Debug log saved to:[/cyan] {debug_logger.get_log_path()}\n")
        
        # Display result
        console.print(f"\n[bold]Status:[/bold] {result.status.value}")
        console.print(f"[bold]Time:[/bold] {result.total_time_seconds:.2f}s\n")
        
        if result.final_output:
            console.print(Panel(
                Markdown(result.final_output),
                title="Output",
                border_style="green",
            ))
        
        if result.escalated:
            console.print(f"\n[yellow]⚠️  Escalated:[/yellow] {result.escalation_reason}")
    
    run_async(quick_execute())


if __name__ == "__main__":
    cli()
