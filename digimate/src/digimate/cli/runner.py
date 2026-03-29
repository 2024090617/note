"""Interactive and non-interactive execution loops."""

from __future__ import annotations

import json
import sys

from digimate.core.agent import Agent


def run_interactive(agent: Agent) -> None:
    """Run interactive CLI loop."""
    print(f"digimate — {agent.config.backend}/{agent.config.model}")
    print(f"workdir: {agent.config.workdir}")
    print("Type /help for commands, or just chat.\n")

    if not agent.check_connection():
        print("⚠  LLM backend not reachable.", file=sys.stderr)

    while True:
        try:
            user_input = input("> ").strip()
            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                if not _handle_command(agent, user_input):
                    break
                continue

            # Chat (read-only)
            def _on_thought(data):
                t = (data or {}).get("thought", "")
                if t:
                    print(f"  💭 {t[:120]}", file=sys.stderr)

            def _on_action(data):
                data = data or {}
                icon = "✓" if data.get("success") else "✗"
                print(f"  {icon} {data.get('action', '?')}", file=sys.stderr)

            agent.on("thought", _on_thought)
            agent.on("action_result", _on_action)

            result = agent.run_task(user_input, read_only=True, preserve_working_memory=True)
            if result.summary:
                print(f"\n{result.summary}\n")

        except KeyboardInterrupt:
            print("\nUse /quit to exit")
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


def run_non_interactive(agent: Agent, task: str, output_json: bool = False) -> None:
    """Run a single task and exit."""
    result = agent.run_task(task)

    if output_json:
        output = {
            "task": task,
            "success": not bool(result.error),
            "summary": result.summary,
            "error": result.error,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.summary:
            print(result.summary)
        if result.error:
            print(f"\nError: {result.error}", file=sys.stderr)
            sys.exit(1)


# ── Slash command dispatch ───────────────────────────────────────────

def _handle_command(agent: Agent, raw: str) -> bool:
    """Handle a slash command. Returns False to quit."""
    parts = raw[1:].split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handlers = {
        "help": _cmd_help,
        "quit": _cmd_quit,
        "exit": _cmd_quit,
        "status": _cmd_status,
        "task": _cmd_task,
        "model": _cmd_model,
        "save": _cmd_save,
        "load": _cmd_load,
        "clear": _cmd_clear,
        "memory": _cmd_memory,
    }

    handler = handlers.get(cmd)
    if handler:
        return handler(agent, args)
    print(f"Unknown command: /{cmd}. Type /help.")
    return True


def _cmd_help(_agent: Agent, _args: str) -> bool:
    print("""
Commands:
  /help              Show this message
  /quit, /exit       Exit
  /status            Show agent status
  /task <desc>       Run an autonomous task
  /model <name>      Set model
  /save <path>       Save session
  /load <path>       Load session
  /clear             Clear conversation
  /memory            Show memory files

Chat:  Just type without a slash.
""")
    return True


def _cmd_quit(_agent: Agent, _args: str) -> bool:
    print("Goodbye!")
    return False


def _cmd_status(agent: Agent, _args: str) -> bool:
    for k, v in agent.status().items():
        print(f"  {k}: {v}")
    return True


def _cmd_task(agent: Agent, args: str) -> bool:
    if not args.strip():
        print("Usage: /task <description>")
        return True

    def _on_thought(data):
        t = (data or {}).get("thought", "")
        if t:
            print(f"  💭 {t[:120]}", file=sys.stderr)

    def _on_action(data):
        data = data or {}
        icon = "✓" if data.get("success") else "✗"
        print(f"  {icon} {data.get('action', '?')}", file=sys.stderr)

    agent.on("thought", _on_thought)
    agent.on("action_result", _on_action)

    result = agent.run_task(args.strip())
    if result.summary:
        print(f"\n{result.summary}\n")
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
    return True


def _cmd_model(agent: Agent, args: str) -> bool:
    if not args.strip():
        print(f"Current model: {agent.config.model}")
        return True
    agent.config.model = args.strip()
    agent._client = None  # reset
    print(f"Model set to: {args.strip()}")
    return True


def _cmd_save(agent: Agent, args: str) -> bool:
    path = args.strip() or "session.json"
    agent.save_session(path)
    print(f"Session saved to {path}")
    return True


def _cmd_load(agent: Agent, args: str) -> bool:
    if not args.strip():
        print("Usage: /load <path>")
        return True
    agent.load_session(args.strip())
    print(f"Session loaded from {args.strip()}")
    return True


def _cmd_clear(agent: Agent, _args: str) -> bool:
    agent.session = type(agent.session)()
    agent.working_memory.clear()
    print("Conversation cleared.")
    return True


def _cmd_memory(agent: Agent, _args: str) -> bool:
    items = agent.memory.list_memories()
    if not items:
        print("No memory files.")
    else:
        for item in items:
            print(f"  {item}")
    return True
