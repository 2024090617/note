"""ReAct-loop agent — simplified from llm-service."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from digimate.core.config import AgentConfig
from digimate.core.content import truncate_observation
from digimate.core.log import Tracer, create_tracer
from digimate.core.types import AgentResponse, ChatMessage, ToolResult
from digimate.llm.base import LLMClient
from digimate.llm.copilot import CopilotBridgeClient
from digimate.llm.openai_compat import OpenAICompatClient
from digimate.memory.markdown import MarkdownMemory
from digimate.memory.working import WorkingMemory
from digimate.prompt.system import build_system_prompt, render_tools_block
from digimate.session.budget import ContextBudgetManager
from digimate.session.compact import maybe_compact
from digimate.session.session import Session
from digimate.skills.loader import discover_skills, render_skills_block
from digimate.tools.base import ToolRegistry
from digimate.tools.file_ops import make_file_tools, make_web_tools
from digimate.tools.git_ops import make_git_tools
from digimate.tools.mcp import MCPManager, make_mcp_tools
from digimate.tools.sandbox import make_sandbox_tools
from digimate.tools.search_ops import make_search_tools
from digimate.tools.terminal import make_terminal_tools
from digimate.workspace.rules import discover_instruction_files
from digimate.workspace.scanner import scan_workspace


class Agent:
    """Autonomous developer agent using the ReAct (Reason + Act) pattern."""

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or AgentConfig()
        workdir = self.config.workdir

        # Core components
        self.tools = ToolRegistry(workdir=workdir)
        self.session = Session()
        self.budget = ContextBudgetManager(
            context_window=self.config.context_window,
            response_reserve=self.config.response_reserve,
        )
        self.working_memory = WorkingMemory(
            max_items=30, max_tokens=self.budget.limit("working_memory"),
        )
        self.session_id = uuid.uuid4().hex[:12]
        self.tracer: Tracer = create_tracer(
            session_id=self.session_id,
            stderr=self.config.trace_stderr,
            file=self.config.trace_file,
            trace_dir=str(Path(workdir) / self.config.trace_dir),
        )

        # LLM client
        self._client: Optional[LLMClient] = None
        self._callbacks: Dict[str, Callable] = {}
        self._read_only = False

        # Memory
        if self.config.memory_strategy == "none":
            self.memory = None
        else:
            self.memory = MarkdownMemory(
                workdir, memory_dir=self.config.memory_dir,
            )

        # MCP (optional)
        self.mcp_manager: Optional[MCPManager] = None
        if self.config.mcp_config_path:
            try:
                self.mcp_manager = MCPManager.from_config_file(self.config.mcp_config_path)
            except Exception:
                pass

        # Register all tools
        self._register_tools()

    # ── Tool registration ────────────────────────────────────────────

    def _register_tools(self) -> None:
        resolve = self.tools.resolve_path
        cfg = self.config
        workdir = cfg.workdir

        for name, (fn, mut) in make_file_tools(
            resolve, read_file_auto_limit=cfg.read_file_auto_limit,
        ).items():
            self.tools.register(name, fn, category="file", mutating=mut)

        for name, (fn, mut) in make_web_tools(
            resolve, web_preview_lines=cfg.web_preview_lines,
        ).items():
            self.tools.register(name, fn, category="web", mutating=mut)

        for name, (fn, mut) in make_search_tools(resolve).items():
            self.tools.register(name, fn, category="search", mutating=mut)

        for name, (fn, mut) in make_terminal_tools(
            resolve, workdir=workdir, command_output_limit=cfg.command_output_limit,
        ).items():
            self.tools.register(name, fn, category="terminal", mutating=mut)

        for name, (fn, mut) in make_git_tools(workdir).items():
            self.tools.register(name, fn, category="git", mutating=mut)

        for name, (fn, mut) in make_sandbox_tools(workdir).items():
            self.tools.register(name, fn, category="sandbox", mutating=mut)

        if self.mcp_manager:
            for name, (fn, mut) in make_mcp_tools(self.mcp_manager).items():
                self.tools.register(name, fn, category="mcp", mutating=mut)

        # Memory + working-memory tool actions
        if self.memory is not None:
            self.tools.register("memory_store", self._handle_memory_store, category="memory", mutating=True)
            self.tools.register("memory_recall", self._handle_memory_recall, category="memory")
            self.tools.register("memory_list", self._handle_memory_list, category="memory")
        self.tools.register("wm_note", self._handle_wm_note, category="memory", mutating=True)
        self.tools.register("wm_remove", self._handle_wm_remove, category="memory", mutating=True)
        self.tools.register("wm_read", self._handle_wm_read, category="memory")

        # Skill invocation
        self.tools.register("use_skill", self._handle_use_skill, category="skills")
        self.tools.register("list_skills", self._handle_list_skills, category="skills")

    # ── LLM client ───────────────────────────────────────────────────

    @property
    def client(self) -> LLMClient:
        if self._client is None:
            if self.config.backend == "copilot":
                self._client = CopilotBridgeClient(
                    model=self.config.model,
                    host=self.config.copilot_host,
                    port=self.config.copilot_port,
                )
            else:
                self._client = OpenAICompatClient(
                    model=self.config.model,
                    api_base=self.config.api_base or "http://localhost:11434/v1",
                    api_key=self.config.api_key,
                )
        return self._client

    # ── Events ───────────────────────────────────────────────────────

    def on(self, event: str, callback: Callable) -> None:
        self._callbacks[event] = callback

    def _emit(self, event: str, data: Any = None) -> None:
        if event in self._callbacks:
            self._callbacks[event](data)

    # ── Public API ───────────────────────────────────────────────────

    def check_connection(self) -> bool:
        try:
            return self.client.is_available()
        except Exception:
            return False

    def chat(self, user_input: str) -> str:
        result = self.run_task(user_input, read_only=True, preserve_working_memory=True)
        return result.summary or ""

    def run_task(
        self,
        task: str,
        max_iterations: Optional[int] = None,
        read_only: bool = False,
        preserve_working_memory: bool = False,
    ) -> AgentResponse:
        self._read_only = read_only
        max_iter = max_iterations or (
            self.config.max_chat_iterations if read_only else self.config.max_iterations
        )

        if not preserve_working_memory:
            self.working_memory.clear()

        self.tracer.emit("task_start", task=task[:120], read_only=read_only)

        user_text = task if read_only else f"Task: {task}\n\nAnalyze and execute step by step."
        self.session.add_message("user", user_text)

        self._emit("task_start", {"task": task})

        try:
            last_action: Optional[str] = None
            last_action_input: Optional[Dict] = None
            repeats = 0

            for iteration in range(max_iter):
                self._emit("iteration_start", {"iteration": iteration + 1})

                response = self._get_llm_response()

                if response.error:
                    self.tracer.emit("iter", n=iteration + 1, action="llm_call",
                                     ok=False, error=response.error[:80])
                    self.tracer.emit("task_end", status="failed", error=response.error[:80])
                    return response

                self._emit("thought", {"thought": response.thought})

                # Loop detection — only trigger if same action WITH same params
                if response.action and not response.is_complete:
                    if (response.action == last_action
                            and response.action_input == last_action_input):
                        repeats += 1
                    else:
                        last_action = response.action
                        last_action_input = response.action_input
                        repeats = 1
                    if repeats >= 3:
                        self.tracer.emit("task_end", status="loop-break", action=response.action)
                        return AgentResponse(
                            is_complete=True,
                            summary=f"Stuck repeating `{response.action}`. Please rephrase.",
                        )

                if response.is_complete:
                    self.tracer.emit("iter", n=iteration + 1, action="complete",
                                     ok=True, thought=response.thought[:80],
                                     summary=(response.summary or "")[:80])
                    self.tracer.emit("task_end", status="completed", iters=iteration + 1)
                    return response

                # Execute action
                if response.action:
                    result = self._execute_action(response.action, response.action_input or {})
                    response.action_result = result.output if result.success else f"Error: {result.error}"

                    obs_tokens = len(response.action_result) // 4
                    self.tracer.emit("iter", n=iteration + 1,
                                     action=response.action, ok=result.success,
                                     tokens=obs_tokens, thought=response.thought[:80],
                                     error=(result.error or "")[:60])

                    self._emit("action_result", {
                        "action": response.action, "success": result.success,
                        "output": response.action_result,
                    })
                    self.session.add_message("user", f"Observation from {response.action}:\n{response.action_result}")
                    self.session.add_action(response.action, response.action_input, result.success)

            self.tracer.emit("task_end", status="incomplete", reason="max_iterations")
            return AgentResponse(is_complete=True, summary="Max iterations reached.", error="max_iterations_exceeded")

        except Exception as e:
            self.tracer.emit("task_end", status="failed", error=str(e)[:80])
            raise
        finally:
            self._read_only = False

    # ── Internal: LLM call ───────────────────────────────────────────

    def _get_llm_response(self) -> AgentResponse:
        system_prompt = self._build_system_prompt()

        # Budget tracking + auto-compact
        self.budget.reset()
        self.budget.record("system_prompt", system_prompt)
        history_text = "\n".join(m.content for m in self.session.get_messages())
        self.budget.record("history", history_text)

        if self.config.auto_compact and self.budget.is_over_budget():
            self.tracer.emit("compact", before=self.budget.total_used)
            maybe_compact(self.session, self.budget)
            history_text = "\n".join(m.content for m in self.session.get_messages())
            self.budget.record("history", history_text)

        snap = self.budget.snapshot()
        total = snap.get("_total", {})
        self.tracer.emit("budget", used=total.get("used", 0),
                         limit=total.get("limit", 0),
                         remaining=total.get("remaining", 0))

        messages = [ChatMessage(role="system", content=system_prompt)]
        for msg in self.session.get_messages():
            messages.append(ChatMessage(role=msg.role, content=msg.content))

        try:
            resp = self.client.chat(messages, model=self.config.model)
            self.session.add_message("assistant", resp.content)
            return self._parse_response(resp.content)
        except Exception as e:
            return AgentResponse(error=str(e))

    def _build_system_prompt(self) -> str:
        cfg = self.config
        workdir = cfg.workdir

        # Workspace
        manifest = scan_workspace(workdir, cache=True)
        workspace_block = manifest.render()

        # Instructions
        instructions = discover_instruction_files(workdir)

        # Tools
        tools_block = render_tools_block(self.tools.list_tools())

        # MCP
        mcp_block = self.mcp_manager.get_tools_summary() if self.mcp_manager else ""

        # Skills
        skills = discover_skills(workdir)
        skills_block = render_skills_block(skills)

        # Memory
        memory_block = ""
        if self.memory is not None:
            try:
                mem_budget = self.budget.remaining("memory")
                memory_block = self.memory.get_prompt_context(max_tokens=mem_budget)
            except Exception:
                pass

        # Working memory
        wm_budget = self.budget.remaining("working_memory")
        wm_block = self.working_memory.render(max_tokens=wm_budget)

        # Read-only suffix
        extra = []
        if self._read_only:
            blocked = ", ".join(f"`{t}`" for t in sorted(self.tools.mutating_tools()))
            extra.append(
                f"## Chat Mode\nYou are in **read-only** mode. Blocked actions: {blocked}. "
                "For file changes, tell the user to use `/task`."
            )

        return build_system_prompt(
            tools_block=tools_block,
            mcp_block=mcp_block,
            skills_block=skills_block,
            workspace_block=workspace_block,
            instructions=instructions,
            memory_block=memory_block,
            working_memory_block=wm_block,
            extra_sections=extra or None,
        )

    # ── Response parsing ─────────────────────────────────────────────

    @staticmethod
    def _parse_response(content: str) -> AgentResponse:
        response = AgentResponse(raw_response=content)
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                response.thought = data.get("thought")
                response.action = data.get("action")
                response.action_input = data.get("action_input", {})
                if response.action == "complete":
                    response.is_complete = True
                    ai = response.action_input or {}
                    short_summary = ai.get("summary", "")
                    # Build full summary: thought (detailed reasoning) + short summary
                    parts = []
                    if response.thought:
                        parts.append(response.thought)
                    if short_summary and short_summary != response.thought:
                        parts.append(short_summary)
                    # Include any text outside the JSON fence (some LLMs put detail there)
                    pre_json = content[:json_match.start()].strip()
                    post_json = content[json_match.end():].strip()
                    if pre_json:
                        parts.insert(0, pre_json)
                    if post_json:
                        parts.append(post_json)
                    response.summary = "\n\n".join(parts) if parts else content
            except json.JSONDecodeError:
                response.is_complete = True
                response.summary = content
        else:
            response.is_complete = True
            response.summary = content
        return response

    # ── Action execution ─────────────────────────────────────────────

    def _execute_action(self, action: str, params: Dict[str, Any]) -> ToolResult:
        # Read-only guard
        tool = self.tools.get(action)
        if self._read_only and tool and tool.mutating:
            return ToolResult(
                False, "", f"'{action}' not allowed in chat mode. Use /task instead."
            )

        result = self.tools.execute(action, params)

        # Layer 1 universal truncation
        if result.success and result.output:
            text, overflow = truncate_observation(
                result.output,
                max_tokens=self.config.max_observation_tokens,
                action=action,
                overflow_dir=str(Path(self.config.workdir) / self.config.overflow_dir),
            )
            if overflow:
                self.tracer.emit("truncate", action=action, overflow=overflow)
                result = ToolResult(
                    success=True, output=text, error=result.error,
                    data=result.data, truncated=True, overflow_path=overflow,
                )

        return result

    # ── Memory / WM handlers ────────────────────────────────────────

    def _handle_memory_store(self, content: str, topic: Optional[str] = None) -> ToolResult:
        if not content:
            return ToolResult(False, "", "content is required")
        try:
            msg = self.memory.store(content, topic)
            return ToolResult(True, msg)
        except Exception as e:
            return ToolResult(False, "", str(e))

    def _handle_memory_recall(self, query: str, limit: int = 5) -> ToolResult:
        if not query:
            return ToolResult(False, "", "query is required")
        entries = self.memory.recall(query, limit=limit)
        if not entries:
            return ToolResult(True, "No matching memories.")
        lines = [f"Found {len(entries)} memories:"]
        for e in entries:
            lines.append(f"  - (score: {e.score:.2f}) {e.content}")
        return ToolResult(True, "\n".join(lines))

    def _handle_memory_list(self) -> ToolResult:
        items = self.memory.list_memories()
        if not items:
            return ToolResult(True, "No memory files.")
        return ToolResult(True, "\n".join(f"  {i}" for i in items))

    def _handle_wm_note(self, key: str, content: str, priority: int = 1) -> ToolResult:
        if not key or not content:
            return ToolResult(False, "", "key and content are required")
        self.working_memory.add_note(key, content, priority)
        return ToolResult(True, f"Note '{key}' saved.")

    def _handle_wm_remove(self, key: str) -> ToolResult:
        if self.working_memory.remove_note(key):
            return ToolResult(True, f"Removed '{key}'")
        return ToolResult(False, "", f"Key '{key}' not found")

    def _handle_wm_read(self) -> ToolResult:
        rendered = self.working_memory.render()
        return ToolResult(True, rendered or "Working memory is empty.")

    # ── Skill handlers ───────────────────────────────────────────────

    def _handle_use_skill(self, skill_name: str) -> ToolResult:
        if not skill_name:
            return ToolResult(False, "", "skill_name is required")
        skills = discover_skills(self.config.workdir)
        for s in skills:
            if s.name == skill_name:
                return ToolResult(True, s.load())
        return ToolResult(False, "", f"Skill '{skill_name}' not found")

    def _handle_list_skills(self) -> ToolResult:
        skills = discover_skills(self.config.workdir)
        if not skills:
            return ToolResult(True, "No skills found.")
        lines = [f"{s.name}: {s.description}" for s in skills]
        return ToolResult(True, "\n".join(lines))

    # ── Status ───────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.config.backend,
            "model": self.config.model,
            "workdir": self.config.workdir,
            "connected": self.check_connection(),
            "session_id": self.session.id,
            "messages": len(self.session.messages),
            "budget": self.budget.snapshot(),
            "working_memory": len(self.working_memory._notes),
        }

    def save_session(self, path: str) -> None:
        self.session.save(path)

    def load_session(self, path: str) -> None:
        self.session = Session.load(path)
