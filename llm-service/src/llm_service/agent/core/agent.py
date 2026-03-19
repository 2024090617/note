"""Agent class - ReAct-style autonomous developer agent."""

import json
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..copilot_client import CopilotBridgeClient, ChatMessage, CopilotBridgeError
from ..session import Session, SessionState, Action, ActionType, ContextBudgetManager, WorkingMemory
from ..tools import ToolRegistry, ToolResult
from ..logger import AgentLogger, LogLevel
from ..skills import create_skill_manager
from ..mcp import MCPManager
from ..memory import create_memory_manager, MemoryStrategy
from ..context import TopicDetector, ConversationIndex

from .config import AgentConfig, AgentMode, AgentResponse
from .delegation import DelegationEngine
from .roles import RoleRegistry
from .prompt import DEVELOPER_AGENT_SYSTEM_PROMPT


class Agent:
    """
    Autonomous developer agent using ReAct pattern.

    The agent:
    1. Receives a task/goal
    2. Reasons about what to do (Thought)
    3. Takes an action (Act)
    4. Observes the result (Observe)
    5. Repeats until task is complete
    """

    def __init__(self, config: Optional[AgentConfig] = None):
        """
        Initialize the agent.

        Args:
            config: Agent configuration
        """
        self.config = config or AgentConfig()
        self.session = Session(
            mode=self.config.mode.value,
            model=self.config.model,
            workdir=self.config.workdir,
            system_prompt=self.config.system_prompt or DEVELOPER_AGENT_SYSTEM_PROMPT,
        )
        self.tools = ToolRegistry(workdir=self.config.workdir)
        self._client: Optional[CopilotBridgeClient] = None
        self._callbacks: Dict[str, Callable] = {}

        # Initialize logger
        self.logger = AgentLogger(
            log_dir=self.config.log_dir,
            log_to_file=self.config.log_to_file,
            log_to_console=self.config.log_to_console,
            console_level=LogLevel.DEBUG if self.config.verbose else LogLevel.INFO,
        )

        # Initialize skill manager (multi-location discovery)
        self.skill_manager = create_skill_manager(
            project_root=Path(self.config.workdir) if self.config.workdir else None
        )

        # Initialize MCP manager (optional — configured via mcp.json)
        self.mcp_manager: Optional[MCPManager] = None
        if self.config.mcp_config_path:
            try:
                self.mcp_manager = MCPManager.from_config_file(self.config.mcp_config_path)
                self.tools.mcp_manager = self.mcp_manager
            except Exception as e:
                self.logger.log(LogLevel.WARNING, f"Failed to load MCP config: {e}")

        # Initialize memory manager (configurable strategy)
        self.memory_manager: Optional[MemoryStrategy] = None
        if self.config.memory_strategy != "none":
            try:
                self.memory_manager = create_memory_manager(
                    strategy=self.config.memory_strategy,
                    memory_dir=self.config.memory_dir,
                    workdir=self.config.workdir,
                )
            except Exception as e:
                self.logger.log(LogLevel.WARNING, f"Failed to init memory: {e}")

        # Initialize context budget manager
        self.budget = ContextBudgetManager(
            context_window=self.config.context_window,
            response_reserve=self.config.response_reserve,
        )

        # Initialize shared role registry (delegation engine draws from this)
        self.role_registry = RoleRegistry()

        # Initialize working memory (task-scoped scratch-pad)
        self.working_memory = WorkingMemory(
            max_items=30,
            max_tokens=self.budget.limit("working_memory"),
        )

        # Topic isolation + retrieval index
        self.topic_detector = TopicDetector(threshold=self.config.topic_shift_threshold)
        self.conversation_index = ConversationIndex(workdir=self.config.workdir)

    @property
    def client(self) -> CopilotBridgeClient:
        """Get or create LLM client."""
        if self._client is None:
            if self.config.mode == AgentMode.COPILOT:
                self._client = CopilotBridgeClient(
                    host=self.config.copilot_host,
                    port=self.config.copilot_port,
                    model=self.config.model,
                )
            else:
                # For github-models mode, we'd use the existing LLMClient
                # For now, default to Copilot bridge
                self._client = CopilotBridgeClient(
                    model=self.config.model,
                )
        return self._client

    def on(self, event: str, callback: Callable):
        """Register event callback."""
        self._callbacks[event] = callback

    def _emit(self, event: str, data: Any = None):
        """Emit event to callbacks."""
        if event in self._callbacks:
            self._callbacks[event](data)

    def check_connection(self) -> bool:
        """Check if LLM backend is available."""
        try:
            return self.client.is_available()
        except Exception:
            return False

    def get_available_models(self) -> List[str]:
        """Get available models from the backend."""
        try:
            models = self.client.get_models()
            return [m.family for m in models]
        except CopilotBridgeError:
            return []

    def set_mode(self, mode: str):
        """Set operating mode."""
        self.config.mode = AgentMode(mode)
        self.session.mode = mode
        self._client = None  # Reset client

    def set_model(self, model: str):
        """Set model to use."""
        self.config.model = model
        self.session.model = model
        if self._client:
            self._client.model = model

    def set_workdir(self, path: str):
        """Set working directory."""
        self.config.workdir = str(Path(path).resolve())
        self.session.workdir = self.config.workdir
        self.tools.set_workdir(self.config.workdir)
        self.conversation_index = ConversationIndex(workdir=self.config.workdir)

    def set_system_prompt(self, prompt: str):
        """Set system prompt."""
        self.config.system_prompt = prompt
        self.session.system_prompt = prompt

    def chat(self, user_input: str) -> str:
        """
        Send a message and get a response (simple chat mode).

        Args:
            user_input: User message

        Returns:
            Assistant response
        """
        recent_context = "\n".join(
            m.content
            for m in self.session.get_thread_messages(limit=self.config.context_recent_messages)
            if m.role == "user"
        )
        if self.topic_detector.is_topic_shift(recent_context, user_input):
            self.session.create_thread(topic=self._topic_label_from_message(user_input), switch=True)

        user_msg = self.session.add_message("user", user_input)
        if user_msg.thread_id:
            self.conversation_index.index_message(
                message_id=user_msg.id,
                thread_id=user_msg.thread_id,
                role=user_msg.role,
                content=user_msg.content,
            )

        messages = self._build_curated_chat_messages(query=user_input)

        try:
            response = self.client.chat(messages, model=self.config.model)
            assistant_msg = self.session.add_message("assistant", response.content)
            if assistant_msg.thread_id:
                self.conversation_index.index_message(
                    message_id=assistant_msg.id,
                    thread_id=assistant_msg.thread_id,
                    role=assistant_msg.role,
                    content=assistant_msg.content,
                )
            return response.content
        except CopilotBridgeError as e:
            error_msg = f"Error: {e}"
            return error_msg

    def _topic_label_from_message(self, text: str) -> str:
        """Derive a short topic slug from user input."""
        words = re.findall(r"\w+", text.lower())
        return "-".join(words[:4]) if words else "general"

    def _build_retrieved_context_block(self, query: str) -> str:
        """Build retrieval block from indexed conversation and memory."""
        scope = self.session.focus_thread_id
        if scope in (None, "current"):
            thread_scope = self.session.current_thread_id
        elif scope == "all":
            thread_scope = None
        else:
            thread_scope = scope

        snippets = self.conversation_index.search(
            query=query,
            limit=self.config.context_retrieval_limit,
            thread_id=thread_scope,
        )

        lines: List[str] = []
        if snippets:
            scope_label = thread_scope or "all"
            lines.append(f"<retrieved_conversation scope=\"{scope_label}\">")
            for item in snippets:
                doc_id = str(item.get("doc_id", ""))
                content = str(item.get("content", "")).replace("\n", " ").strip()
                lines.append(f"  <snippet source=\"{doc_id}\">{content[:280]}</snippet>")
            lines.append("</retrieved_conversation>")

        if self.memory_manager:
            try:
                memories = self.memory_manager.recall(query, limit=3)
            except Exception:
                memories = []
            if memories:
                lines.append("<retrieved_memory>")
                for mem in memories:
                    source = mem.source or "memory"
                    lines.append(
                        f"  <memory source=\"{source}\" score=\"{mem.score:.2f}\">{mem.content[:240]}</memory>"
                    )
                lines.append("</retrieved_memory>")

        return "\n".join(lines)

    def _build_curated_chat_messages(self, query: str) -> List[ChatMessage]:
        """Build thread-scoped chat messages with optional retrieval context."""
        messages = [
            ChatMessage(
                role="system",
                content=self.session.system_prompt or DEVELOPER_AGENT_SYSTEM_PROMPT,
            ),
        ]

        current_thread = self.session.get_current_thread() or {}
        thread_topic = current_thread.get("topic", "general")
        thread_summary = current_thread.get("summary") or ""
        if thread_summary:
            messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        f"Current topic: {thread_topic}\n"
                        f"Thread summary: {thread_summary}"
                    ),
                )
            )
        else:
            messages.append(ChatMessage(role="system", content=f"Current topic: {thread_topic}"))

        retrieved = self._build_retrieved_context_block(query)
        if retrieved:
            messages.append(
                ChatMessage(
                    role="system",
                    content=(
                        "Use retrieved context only when relevant to the latest query. "
                        "If unrelated, ignore stale snippets.\n"
                        f"{retrieved}"
                    ),
                )
            )

        for msg in self.session.get_thread_messages(limit=self.config.context_recent_messages):
            messages.append(ChatMessage(role=msg.role, content=msg.content))
        return messages

    def run_task(
        self,
        task: str,
        max_iterations: Optional[int] = None,
        preserve_state: bool = False,
        continuation_note: Optional[str] = None,
    ) -> AgentResponse:
        """
        Run an autonomous task using the ReAct loop.

        Args:
            task: Task description
            max_iterations: Maximum iterations (overrides config)
            preserve_state: Keep previous goal/state/working memory for continuation
            continuation_note: Additional continuation guidance for resumed runs

        Returns:
            Final AgentResponse
        """
        max_iter = max_iterations or self.config.max_iterations
        effective_goal = task
        if preserve_state and self.session.state.goal:
            effective_goal = self.session.state.goal
        else:
            self.session.set_goal(task)

        # Reset task-scoped scratch-pad only for new tasks.
        if preserve_state:
            if not self.working_memory.goal:
                self.working_memory.set_goal(effective_goal)
        else:
            self.working_memory.clear()
            self.working_memory.set_goal(effective_goal)

        self.create_checkpoint(
            "task_start",
            metadata={
                "preserve_state": preserve_state,
                "task": task,
            },
        )

        # Start logging the interaction
        self.logger.start_interaction(self.session.id, effective_goal)

        # Initial prompt with task
        if preserve_state:
            continuation_parts = [
                f"Resume task goal: {effective_goal}",
                "Continue from the existing plan/state and improve the current solution.",
            ]
            if continuation_note:
                continuation_parts.append(f"Continuation update: {continuation_note}")
            elif task and task != effective_goal:
                continuation_parts.append(f"Continuation update: {task}")
            resume_msg = self.session.add_message("user", "\n".join(continuation_parts))
            if resume_msg.thread_id:
                self.conversation_index.index_message(
                    message_id=resume_msg.id,
                    thread_id=resume_msg.thread_id,
                    role=resume_msg.role,
                    content=resume_msg.content,
                )
        else:
            task_msg = self.session.add_message(
                "user",
                f"Task: {task}\n\nPlease analyze this task and create a plan, then execute it step by step.",
            )
            if task_msg.thread_id:
                self.conversation_index.index_message(
                    message_id=task_msg.id,
                    thread_id=task_msg.thread_id,
                    role=task_msg.role,
                    content=task_msg.content,
                )

        self._emit("task_start", {"task": task})

        try:
            for iteration in range(max_iter):
                self._emit("iteration_start", {"iteration": iteration + 1})

                # Get LLM response
                response = self._get_llm_response()

                if response.error:
                    self._emit("error", {"error": response.error})
                    self.create_checkpoint(
                        "task_failed",
                        metadata={"error": response.error, "iteration": iteration + 1},
                    )
                    self.logger.end_interaction(status="failed", error=response.error)
                    return response

                self._emit("thought", {"thought": response.thought})

                # Log iteration
                observation = None

                # Check if complete
                if response.is_complete:
                    self._emit("task_complete", {"summary": response.summary})
                    self.create_checkpoint(
                        "task_complete",
                        metadata={"iteration": iteration + 1},
                    )
                    self.logger.log_iteration(
                        iteration=iteration + 1,
                        thought=response.thought,
                        action=response.action,
                        action_input=response.action_input,
                        observation=None,
                        is_complete=True,
                    )
                    self.logger.end_interaction(status="completed", result=response.summary)
                    return response

                # Execute action
                if response.action:
                    action_start = time.time()
                    result = self._execute_action(response.action, response.action_input or {})
                    action_duration = (time.time() - action_start) * 1000

                    response.action_result = result.output if result.success else f"Error: {result.error}"
                    observation = response.action_result

                    # Log tool call
                    self.logger.log_tool_call(
                        tool=response.action,
                        params=response.action_input or {},
                        result=response.action_result,
                        success=result.success,
                        duration_ms=action_duration,
                        error=result.error if not result.success else None,
                    )

                    self._emit(
                        "action_result",
                        {
                            "action": response.action,
                            "success": result.success,
                            "output": response.action_result,
                        },
                    )

                    # Add observation to conversation
                    obs_message = f"Observation from {response.action}:\n{response.action_result}"
                    obs_msg = self.session.add_message("user", obs_message)
                    if obs_msg.thread_id:
                        self.conversation_index.index_message(
                            message_id=obs_msg.id,
                            thread_id=obs_msg.thread_id,
                            role=obs_msg.role,
                            content=obs_msg.content,
                        )

                    # Log action to session
                    self.session.add_action(
                        action_type=self._action_to_type(response.action),
                        description=f"{response.action}: {json.dumps(response.action_input)}",
                        target=response.action_input.get("path") or response.action_input.get("command"),
                        result=response.action_result[:500],
                        success=result.success,
                    )

                # Log iteration
                self.logger.log_iteration(
                    iteration=iteration + 1,
                    thought=response.thought,
                    action=response.action,
                    action_input=response.action_input,
                    observation=observation,
                    is_complete=False,
                )

            # Max iterations reached
            self.create_checkpoint("task_incomplete", metadata={"error": "max_iterations_exceeded"})
            self.logger.end_interaction(status="incomplete", error="max_iterations_exceeded")
            return AgentResponse(
                is_complete=True,
                summary="Maximum iterations reached. Task may be incomplete.",
                error="max_iterations_exceeded",
            )
        except Exception as e:
            self.create_checkpoint("task_failed", metadata={"error": str(e)})
            self.logger.end_interaction(status="failed", error=str(e))
            raise

    def create_checkpoint(
        self,
        label: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a continuation checkpoint for the current session."""
        checkpoint = self.session.create_checkpoint(
            label=label,
            working_memory=self.working_memory.to_dict(),
            metadata=metadata,
        )
        self.logger.debug(f"Checkpoint created: {checkpoint['id']} ({checkpoint['label']})")
        return checkpoint

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List available checkpoints."""
        return self.session.list_checkpoints()

    def resume_checkpoint(self, identifier: Optional[str] = None) -> Dict[str, Any]:
        """Restore task state from a checkpoint by id or label."""
        checkpoint = self.session.get_checkpoint(identifier)
        if not checkpoint:
            raise ValueError(f"Checkpoint not found: {identifier}" if identifier else "No checkpoints available")

        self.session.state = SessionState.from_dict(checkpoint.get("state", {}))
        wm_snapshot = checkpoint.get("working_memory")
        if wm_snapshot:
            self.working_memory = WorkingMemory.from_dict(
                wm_snapshot,
                max_items=self.working_memory.max_items,
                max_tokens=self.working_memory.max_tokens,
            )

        self.logger.info(f"Resumed from checkpoint {checkpoint.get('id')} ({checkpoint.get('label')})")
        return checkpoint

    def _build_system_prompt(self) -> str:
        """Build system prompt with available skills and MCP tools injected.

        Uses the context budget manager to track token usage per component
        so the caller can decide whether compaction is needed.
        """
        base_prompt = self.session.system_prompt or DEVELOPER_AGENT_SYSTEM_PROMPT
        prefix_blocks: List[str] = []

        # Reset budget counters for this turn
        self.budget.reset()

        # Record base prompt cost first
        self.budget.record("system_prompt", base_prompt)

        # Inject available skills (honour budget)
        if self.skill_manager:
            skills = self.skill_manager.list_skills()
            if skills:
                lines = ["<available_skills>"]
                for skill in skills:
                    lines.append(f"  <skill>")
                    lines.append(f"    <name>{skill.name}</name>")
                    lines.append(f"    <description>{skill.description}</description>")
                    lines.append(f"  </skill>")
                lines.append("</available_skills>")
                skills_text = "\n".join(lines)
                self.budget.record("skills", skills_text)
                prefix_blocks.append(skills_text)

        # Inject available MCP tools
        if self.mcp_manager:
            try:
                mcp_summary = self.mcp_manager.get_tools_summary()
                if mcp_summary:
                    self.budget.record("mcp_tools", mcp_summary)
                    prefix_blocks.append(mcp_summary)
            except Exception:
                pass  # Fail silently — MCP servers may not be reachable yet

        # Inject memory context (token-aware)
        if self.memory_manager:
            try:
                mem_budget = self.budget.remaining("memory")
                mem_ctx = self.memory_manager.get_prompt_context(max_tokens=mem_budget)
                if mem_ctx:
                    self.budget.record("memory", mem_ctx)
                    prefix_blocks.append(mem_ctx)
            except Exception:
                pass  # Fail silently — memory may not be readable

        # Inject working memory (task-scoped scratch-pad)
        wm_budget = self.budget.remaining("working_memory")
        wm_block = self.working_memory.render(max_tokens=wm_budget)
        if wm_block:
            self.budget.record("working_memory", wm_block)
            prefix_blocks.append(wm_block)

        if prefix_blocks:
            return "\n\n".join(prefix_blocks) + "\n\n" + base_prompt
        return base_prompt

    def _get_llm_response(self) -> AgentResponse:
        """Get and parse LLM response.

        Builds the system prompt (which records budget for system/skills/mcp/memory),
        then records history tokens.  If the total exceeds the context window and
        auto_compact is enabled, the session is compacted before sending.
        """
        system_prompt = self._build_system_prompt()

        # Record history token usage *before* deciding to compact
        history_text = "\n".join(m.content for m in self.session.get_thread_messages())
        self.budget.record("history", history_text)

        # Auto-compact if over budget
        if self.config.auto_compact and self.budget.is_over_budget():
            self.logger.log(
                LogLevel.INFO,
                f"Context budget exceeded ({self.budget.total_used}/{self.budget.available} tokens). "
                "Compacting session...",
            )
            # Flush memory state before compaction
            if self.memory_manager:
                try:
                    self.memory_manager.flush()
                except Exception:
                    pass
            self.session.compact()
            # Re-record history after compaction
            history_text = "\n".join(m.content for m in self.session.get_thread_messages())
            self.budget.record("history", history_text)

        messages = [
            ChatMessage(role="system", content=system_prompt),
        ]

        for msg in self.session.get_thread_messages():
            messages.append(ChatMessage(role=msg.role, content=msg.content))

        # Log the request
        msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
        self.logger.log_llm_request(self.config.model, msg_dicts)

        start_time = time.time()
        try:
            response = self.client.chat(messages, model=self.config.model)
            content = response.content
            duration_ms = (time.time() - start_time) * 1000

            # Log the response
            self.logger.log_llm_response(
                model=self.config.model,
                messages=msg_dicts,
                response=content,
                duration_ms=duration_ms,
            )

            assistant_msg = self.session.add_message("assistant", content)
            if assistant_msg.thread_id:
                self.conversation_index.index_message(
                    message_id=assistant_msg.id,
                    thread_id=assistant_msg.thread_id,
                    role=assistant_msg.role,
                    content=assistant_msg.content,
                )

            return self._parse_response(content)

        except CopilotBridgeError as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_llm_response(
                model=self.config.model,
                messages=msg_dicts,
                response="",
                duration_ms=duration_ms,
                error=str(e),
            )
            return AgentResponse(error=str(e))

    def _parse_response(self, content: str) -> AgentResponse:
        """Parse LLM response to extract thought/action."""
        response = AgentResponse(raw_response=content)

        # Try to extract JSON block
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)

        if json_match:
            try:
                data = json.loads(json_match.group(1))
                response.thought = data.get("thought")
                response.action = data.get("action")
                response.action_input = data.get("action_input", {})

                if response.action == "complete":
                    response.is_complete = True
                    response.summary = response.action_input.get("summary", content)

            except json.JSONDecodeError:
                # Fallback: treat as conversational response
                response.is_complete = True
                response.summary = content
        else:
            # No JSON found, treat as conversational
            response.is_complete = True
            response.summary = content

        return response

    def _execute_action(self, action: str, params: Dict[str, Any]) -> ToolResult:
        """Execute an action using the tool registry."""
        action_map = {
            "read_file": lambda p: self.tools.read_file(
                p.get("path", ""),
                p.get("start_line", 1),
                p.get("end_line"),
            ),
            "write_file": lambda p: self.tools.write_file(
                p.get("path", ""),
                p.get("content", ""),
            ),
            "create_file": lambda p: self.tools.create_file(
                p.get("path", ""),
                p.get("content", ""),
            ),
            "list_directory": lambda p: self.tools.list_directory(
                p.get("path", "."),
            ),
            "search_files": lambda p: self.tools.search_files(
                p.get("pattern", ""),
                p.get("path", "."),
            ),
            "grep_search": lambda p: self.tools.grep_search(
                p.get("pattern", ""),
                p.get("path", "."),
                p.get("file_pattern", "*"),
            ),
            "run_command": lambda p: self.tools.run_command(
                p.get("command", ""),
                p.get("timeout", 60),
                confirmed=self.config.auto_confirm,
            ),
            "detect_environment": lambda p: self.tools.detect_environment(),
            "git_status": lambda p: self.tools.get_git_status(),
            "use_skill": lambda p: self._handle_use_skill(p.get("skill_name", "")),
            "list_skills": lambda p: self._handle_list_skills(),
            "run_in_docker": lambda p: self.tools.run_in_docker(
                p.get("script", ""),
                p.get("language", "python"),
                p.get("image", ""),
                p.get("timeout", 120),
                p.get("pip_packages"),
                p.get("network", False),
            ),
            "docker_search": lambda p: self.tools.docker_search(
                p.get("query", ""),
                p.get("limit", 5),
            ),
            "docker_pull": lambda p: self.tools.docker_pull(
                p.get("image", ""),
            ),
            "docker_available": lambda p: self.tools.docker_available(),
            "mcp_list_servers": lambda p: self.tools.mcp_list_servers(),
            "mcp_list_tools": lambda p: self.tools.mcp_list_tools(
                p.get("server"),
            ),
            "mcp_call_tool": lambda p: self.tools.mcp_call_tool(
                p.get("server", ""),
                p.get("tool", ""),
                p.get("arguments"),
            ),
            "delegate_review": lambda p: self._handle_delegate_review(
                p.get("task", self.session.goal or ""),
                p.get("candidates", []),
                p.get("focus"),
            ),
            "memory_store": lambda p: self._handle_memory_store(
                p.get("content", ""),
                p.get("topic"),
            ),
            "memory_recall": lambda p: self._handle_memory_recall(
                p.get("query", ""),
                p.get("limit", 5),
            ),
            "memory_list": lambda p: self._handle_memory_list(),
            "wm_note": lambda p: self._handle_wm_note(
                p.get("key", ""),
                p.get("content", ""),
                p.get("priority", 1),
            ),
            "wm_artifact": lambda p: self._handle_wm_artifact(
                p.get("key", ""),
                p.get("data", ""),
                p.get("label", ""),
                p.get("priority", 1),
            ),
            "wm_remove": lambda p: self._handle_wm_remove(
                p.get("key", ""),
            ),
            "wm_read": lambda p: self._handle_wm_read(),
            "plan": lambda p: self._handle_plan(p.get("steps", [])),
            "complete": lambda p: ToolResult(True, p.get("summary", "Task completed")),
        }

        handler = action_map.get(action)
        if handler:
            try:
                return handler(params)
            except Exception as e:
                return ToolResult(False, "", str(e))
        else:
            return ToolResult(False, "", f"Unknown action: {action}")

    def _handle_use_skill(self, skill_name: str) -> ToolResult:
        """Activate a skill and return its full instructions."""
        if not self.skill_manager:
            return ToolResult(False, "", "Skill manager not available")
        if not skill_name:
            return ToolResult(False, "", "skill_name is required")

        content = self.skill_manager.invoke_skill(skill_name)
        if content:
            return ToolResult(True, content)
        return ToolResult(False, "", f"Skill '{skill_name}' not found")

    def _handle_list_skills(self) -> ToolResult:
        """List all available skills."""
        if not self.skill_manager:
            return ToolResult(True, "No skills available (skillkit not installed)")

        skills = self.skill_manager.list_skills()
        if not skills:
            return ToolResult(True, "No skills found in any location")

        lines = [f"Available skills ({len(skills)}):"]
        for s in skills:
            lines.append(f"  - {s.name}: {s.description}")
        return ToolResult(True, "\n".join(lines))

    def _handle_memory_store(self, content: str, topic: Optional[str] = None) -> ToolResult:
        """Store a memory entry."""
        if not self.memory_manager:
            return ToolResult(False, "", "Memory not configured (use --memory-strategy)")
        if not content:
            return ToolResult(False, "", "content is required")
        try:
            msg = self.memory_manager.store(content, topic)
            return ToolResult(True, msg)
        except Exception as e:
            return ToolResult(False, "", f"Failed to store memory: {e}")

    def _handle_delegate_review(
        self,
        task: str,
        candidates: List[Dict[str, Any]],
        focus: Optional[List[str]] = None,
    ) -> ToolResult:
        """Delegate candidate review to specialist sub-agents."""
        if not self.config.enable_delegation:
            return ToolResult(
                False,
                "",
                "Delegation is disabled. Start agent with delegation enabled.",
            )

        if not task.strip():
            return ToolResult(False, "", "task is required")

        if not isinstance(candidates, list) or not candidates:
            return ToolResult(False, "", "candidates must be a non-empty list")

        if isinstance(focus, str):
            focus = [focus]
        elif focus is not None and not isinstance(focus, list):
            focus = None

        max_candidates = max(1, int(self.config.max_candidate_pages))
        limited_candidates = candidates[:max_candidates]
        try:
            engine = DelegationEngine(
                client=self.client,
                model=self.config.model,
                max_specialists=self.config.max_specialists,
                max_collab_rounds=self.config.max_collab_rounds,
                registry=self.role_registry,
            )
            result = engine.review_candidates(task, limited_candidates, focus)
            if not result.get("success"):
                return ToolResult(False, "", str(result.get("error", "Delegation failed")))

            lines = ["Delegated specialist review completed.", "", "Synthesis:", result.get("synthesis", "")]
            specialists = result.get("specialists") or []
            if specialists:
                lines.append("")
                lines.append("Specialist outputs:")
                for item in specialists:
                    role = item.get("role", "specialist")
                    review = str(item.get("review", "")).strip()
                    lines.append(f"- {role}: {review[:700]}")

            return ToolResult(True, "\n".join(lines), data=result)
        except Exception as e:
            return ToolResult(False, "", f"Delegation failed: {e}")

    def _handle_memory_recall(self, query: str, limit: int = 5) -> ToolResult:
        """Search stored memories."""
        if not self.memory_manager:
            return ToolResult(False, "", "Memory not configured (use --memory-strategy)")
        if not query:
            return ToolResult(False, "", "query is required")
        try:
            thread = self.session.get_current_thread()
            scoped_query = query
            if thread and thread.get("topic"):
                scoped_query = f"{query} {thread['topic']}"
            entries = self.memory_manager.recall(scoped_query, limit=limit)
            if not entries:
                return ToolResult(True, "No matching memories found.")
            lines = [f"Found {len(entries)} memories:"]
            for e in entries:
                src = f" [{e.source}]" if e.source else ""
                lines.append(f"  - (score: {e.score:.2f}{src}) {e.content}")
            return ToolResult(True, "\n".join(lines))
        except Exception as e:
            return ToolResult(False, "", f"Memory recall failed: {e}")

    def _handle_memory_list(self) -> ToolResult:
        """List all memory files."""
        if not self.memory_manager:
            return ToolResult(False, "", "Memory not configured (use --memory-strategy)")
        try:
            items = self.memory_manager.list_memories()
            if not items:
                return ToolResult(True, "No memory files found.")
            header = f"Memory ({self.memory_manager.name} strategy):"
            return ToolResult(True, header + "\n" + "\n".join(f"  {i}" for i in items))
        except Exception as e:
            return ToolResult(False, "", f"Memory list failed: {e}")

    def _handle_plan(self, steps: List[str]) -> ToolResult:
        """Handle plan action - store plan in session state."""
        self.session.state.plan = steps
        self.session.state.plan_step = 0

        # Also sync to working memory
        self.working_memory.set_goal(self.session.state.goal or "")
        for i, step in enumerate(steps, 1):
            self.working_memory.add_note(
                f"plan-step-{i}", step, priority=2,
            )

        plan_text = "Plan created:\n"
        for i, step in enumerate(steps, 1):
            plan_text += f"  {i}. {step}\n"

        return ToolResult(True, plan_text, data={"steps": steps})

    # ------------------------------------------------------------------
    # Working memory handlers
    # ------------------------------------------------------------------

    def _handle_wm_note(self, key: str, content: str, priority: int = 1) -> ToolResult:
        """Add/update a working memory note."""
        if not key.strip():
            return ToolResult(False, "", "key is required")
        if not content.strip():
            return ToolResult(False, "", "content is required")
        try:
            self.working_memory.add_note(key, content, priority=priority)
            return ToolResult(True, f"Working memory note '{key}' updated ({self.working_memory.summary()})")
        except Exception as e:
            return ToolResult(False, "", f"wm_note failed: {e}")

    def _handle_wm_artifact(self, key: str, data: str, label: str = "", priority: int = 1) -> ToolResult:
        """Add/update a working memory artifact."""
        if not key.strip():
            return ToolResult(False, "", "key is required")
        if not data.strip():
            return ToolResult(False, "", "data is required")
        try:
            self.working_memory.add_artifact(key, data, label=label, priority=priority)
            return ToolResult(True, f"Working memory artifact '{key}' stored ({self.working_memory.summary()})")
        except Exception as e:
            return ToolResult(False, "", f"wm_artifact failed: {e}")

    def _handle_wm_remove(self, key: str) -> ToolResult:
        """Remove an item from working memory."""
        if not key.strip():
            return ToolResult(False, "", "key is required")
        removed = self.working_memory.remove_note(key) or self.working_memory.remove_artifact(key)
        if removed:
            return ToolResult(True, f"Removed '{key}' from working memory")
        return ToolResult(False, "", f"Key '{key}' not found in working memory")

    def _handle_wm_read(self) -> ToolResult:
        """Read the current working memory state."""
        rendered = self.working_memory.render()
        if not rendered:
            return ToolResult(True, "Working memory is empty.")
        return ToolResult(True, rendered)

    def _action_to_type(self, action: str) -> ActionType:
        """Map action name to ActionType."""
        mapping = {
            "read_file": ActionType.FILE_READ,
            "write_file": ActionType.FILE_WRITE,
            "create_file": ActionType.FILE_CREATE,
            "list_directory": ActionType.FILE_READ,
            "search_files": ActionType.SEARCH,
            "grep_search": ActionType.SEARCH,
            "run_command": ActionType.COMMAND_RUN,
            "detect_environment": ActionType.COMMAND_RUN,
            "git_status": ActionType.COMMAND_RUN,
            "use_skill": ActionType.LLM_CALL,
            "list_skills": ActionType.LLM_CALL,
            "run_in_docker": ActionType.COMMAND_RUN,
            "docker_search": ActionType.SEARCH,
            "docker_pull": ActionType.COMMAND_RUN,
            "docker_available": ActionType.COMMAND_RUN,
            "mcp_list_servers": ActionType.SEARCH,
            "mcp_list_tools": ActionType.SEARCH,
            "mcp_call_tool": ActionType.LLM_CALL,
            "delegate_review": ActionType.LLM_CALL,
            "memory_store": ActionType.FILE_WRITE,
            "memory_recall": ActionType.SEARCH,
            "memory_list": ActionType.SEARCH,
            "wm_note": ActionType.PLAN,
            "wm_artifact": ActionType.PLAN,
            "wm_remove": ActionType.PLAN,
            "wm_read": ActionType.SEARCH,
            "plan": ActionType.PLAN,
            "complete": ActionType.VERIFY,
        }
        return mapping.get(action, ActionType.LLM_CALL)

    def status(self) -> Dict[str, Any]:
        """Get current agent status."""
        skill_info = None
        if self.skill_manager:
            skill_info = self.skill_manager.get_skill_locations()

        mcp_info = None
        if self.mcp_manager:
            mcp_info = {
                "servers": self.mcp_manager.list_servers(),
                "total_tools": len(self.mcp_manager.list_tools()),
            }

        memory_info = None
        if self.memory_manager:
            memory_info = {
                "strategy": self.memory_manager.name,
                "memory_dir": self.memory_manager.memory_dir,
                "files": len(self.memory_manager.list_memories()),
            }

        return {
            "mode": self.config.mode.value,
            "model": self.config.model,
            "workdir": self.config.workdir,
            "connected": self.check_connection(),
            "session_id": self.session.id,
            "messages": len(self.session.messages),
            "actions": len(self.session.actions),
            "state": self.session.state.summary(),
            "skills": skill_info,
            "mcp": mcp_info,
            "memory": memory_info,
            "budget": self.budget.snapshot(),
            "roles": self.role_registry.list_names(),
            "working_memory": self.working_memory.summary(),
            "threads": len(self.session.threads),
            "current_topic": (self.session.get_current_thread() or {}).get("topic"),
            "focus": self.session.focus_thread_id or "current",
        }

    def save_session(self, path: str):
        """Save current session to file."""
        self.session.save(path)

    def load_session(self, path: str):
        """Load session from file."""
        self.session = Session.load(path)
        self.config.mode = AgentMode(self.session.mode)
        self.config.model = self.session.model
        self.config.workdir = self.session.workdir
        self.tools.set_workdir(self.session.workdir)
        self.conversation_index = ConversationIndex(workdir=self.config.workdir)
        for msg in self.session.messages:
            target_thread = msg.thread_id or self.session.current_thread_id
            if not target_thread:
                continue
            self.conversation_index.index_message(
                message_id=msg.id,
                thread_id=target_thread,
                role=msg.role,
                content=msg.content,
            )
