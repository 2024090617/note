"""Main entry point for the agent CLI."""

from ..core import Agent, AgentConfig, AgentMode
from .output import console
from .parser import create_parser
from .runner import run_interactive, run_non_interactive


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
        sandbox_enabled=args.sandbox,
        sandbox_default_image=args.sandbox_image,
        mcp_config_path=getattr(args, "mcp_config", None),
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
            import sys

            sys.exit(1)
        run_non_interactive(agent, task, args.json)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
