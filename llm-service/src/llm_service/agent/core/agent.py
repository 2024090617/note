"""Agent class - ReAct-style autonomous developer agent."""

import json
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..copilot_client import CopilotBridgeClient, ChatMessage, CopilotBridgeError
from ..session import Session, SessionState, Action, ActionType
from ..tools import ToolRegistry, ToolResult
from ..logger import AgentLogger, LogLevel
from ..skills import create_skill_manager
from ..mcp import MCPManager

from .config import AgentConfig, AgentMode, AgentResponse
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
        self.session.add_message("user", user_input)

        messages = [
            ChatMessage(
                role="system",
                content=self.session.system_prompt or DEVELOPER_AGENT_SYSTEM_PROMPT,
            ),
        ]

        for msg in self.session.messages:
            messages.append(ChatMessage(role=msg.role, content=msg.content))

        try:
            response = self.client.chat(messages, model=self.config.model)
            self.session.add_message("assistant", response.content)
            return response.content
        except CopilotBridgeError as e:
            error_msg = f"Error: {e}"
            return error_msg

    def run_task(self, task: str, max_iterations: Optional[int] = None) -> AgentResponse:
        """
        Run an autonomous task using the ReAct loop.

        Args:
            task: Task description
            max_iterations: Maximum iterations (overrides config)

        Returns:
            Final AgentResponse
        """
        max_iter = max_iterations or self.config.max_iterations
        self.session.set_goal(task)

        # Start logging the interaction
        self.logger.start_interaction(self.session.id, task)

        # Initial prompt with task
        self.session.add_message(
            "user",
            f"Task: {task}\n\nPlease analyze this task and create a plan, then execute it step by step.",
        )

        self._emit("task_start", {"task": task})

        try:
            for iteration in range(max_iter):
                self._emit("iteration_start", {"iteration": iteration + 1})

                # Get LLM response
                response = self._get_llm_response()

                if response.error:
                    self._emit("error", {"error": response.error})
                    self.logger.end_interaction(status="failed", error=response.error)
                    return response

                self._emit("thought", {"thought": response.thought})

                # Log iteration
                observation = None

                # Check if complete
                if response.is_complete:
                    self._emit("task_complete", {"summary": response.summary})
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
                    self.session.add_message("user", obs_message)

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
            self.logger.end_interaction(status="incomplete", error="max_iterations_exceeded")
            return AgentResponse(
                is_complete=True,
                summary="Maximum iterations reached. Task may be incomplete.",
                error="max_iterations_exceeded",
            )
        except Exception as e:
            self.logger.end_interaction(status="failed", error=str(e))
            raise

    def _build_system_prompt(self) -> str:
        """Build system prompt with available skills and MCP tools injected."""
        base_prompt = self.session.system_prompt or DEVELOPER_AGENT_SYSTEM_PROMPT
        prefix_blocks: List[str] = []

        # Inject available skills
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
                prefix_blocks.append("\n".join(lines))

        # Inject available MCP tools
        if self.mcp_manager:
            try:
                mcp_summary = self.mcp_manager.get_tools_summary()
                if mcp_summary:
                    prefix_blocks.append(mcp_summary)
            except Exception:
                pass  # Fail silently — MCP servers may not be reachable yet

        if prefix_blocks:
            return "\n\n".join(prefix_blocks) + "\n\n" + base_prompt
        return base_prompt

    def _get_llm_response(self) -> AgentResponse:
        """Get and parse LLM response."""
        messages = [
            ChatMessage(
                role="system",
                content=self._build_system_prompt(),
            ),
        ]

        for msg in self.session.messages:
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

            self.session.add_message("assistant", content)

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

    def _handle_plan(self, steps: List[str]) -> ToolResult:
        """Handle plan action - store plan in session state."""
        self.session.state.plan = steps
        self.session.state.plan_step = 0

        plan_text = "Plan created:\n"
        for i, step in enumerate(steps, 1):
            plan_text += f"  {i}. {step}\n"

        return ToolResult(True, plan_text, data={"steps": steps})

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
