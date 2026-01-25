"""
Agent Logger - Detailed logging for interaction tracking.

Records all agent activities: LLM calls, tool executions, decisions, and errors.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum


class LogLevel(str, Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class LLMCallLog:
    """Log entry for an LLM call."""
    timestamp: str
    model: str
    messages_count: int
    messages_preview: str  # First/last messages truncated
    response_preview: str
    response_length: int
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCallLog:
    """Log entry for a tool/action call."""
    timestamp: str
    tool: str
    params: Dict[str, Any]
    result_preview: str
    result_length: int
    success: bool
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IterationLog:
    """Log entry for a ReAct iteration."""
    timestamp: str
    iteration: int
    thought: Optional[str]
    action: Optional[str]
    action_input: Optional[Dict[str, Any]]
    observation_preview: Optional[str]
    is_complete: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InteractionLog:
    """Complete log of an agent interaction/task."""
    session_id: str
    task: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = "running"  # running, completed, failed, cancelled
    iterations: List[IterationLog] = field(default_factory=list)
    llm_calls: List[LLMCallLog] = field(default_factory=list)
    tool_calls: List[ToolCallLog] = field(default_factory=list)
    final_result: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "task": self.task,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "iterations": [i.to_dict() for i in self.iterations],
            "llm_calls": [l.to_dict() for l in self.llm_calls],
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "final_result": self.final_result,
            "error": self.error,
        }
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the interaction."""
        return {
            "session_id": self.session_id,
            "task": self.task[:100] + "..." if len(self.task) > 100 else self.task,
            "status": self.status,
            "iterations": len(self.iterations),
            "llm_calls": len(self.llm_calls),
            "tool_calls": len(self.tool_calls),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class AgentLogger:
    """
    Logger for tracking agent interactions.
    
    Supports:
    - Console output with configurable verbosity
    - File logging in JSON format
    - Structured interaction logs for analysis
    """
    
    def __init__(
        self,
        log_dir: Optional[str] = None,
        console_level: LogLevel = LogLevel.INFO,
        file_level: LogLevel = LogLevel.DEBUG,
        log_to_console: bool = True,
        log_to_file: bool = True,
        max_preview_length: int = 500,
    ):
        """
        Initialize the logger.
        
        Args:
            log_dir: Directory for log files (default: ./agent_logs)
            console_level: Minimum level for console output
            file_level: Minimum level for file output
            log_to_console: Enable console logging
            log_to_file: Enable file logging
            max_preview_length: Max length for content previews
        """
        self.log_dir = Path(log_dir) if log_dir else Path.cwd() / "agent_logs"
        self.console_level = console_level
        self.file_level = file_level
        self.log_to_console = log_to_console
        self.log_to_file = log_to_file
        self.max_preview_length = max_preview_length
        
        self._current_interaction: Optional[InteractionLog] = None
        self._file_handler: Optional[logging.FileHandler] = None
        
        # Setup Python logger for general logging
        self._setup_logger()
        
        # Ensure log directory exists
        if self.log_to_file:
            self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_logger(self):
        """Setup Python logger."""
        self.logger = logging.getLogger("agent")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []  # Clear existing handlers
        
        # Console handler
        if self.log_to_console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(getattr(logging, self.console_level.value))
            console_formatter = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
    
    def _truncate(self, text: str, max_length: Optional[int] = None) -> str:
        """Truncate text for preview."""
        max_len = max_length or self.max_preview_length
        if len(text) <= max_len:
            return text
        return text[:max_len] + f"... [{len(text) - max_len} more chars]"
    
    def _timestamp(self) -> str:
        """Get current timestamp."""
        return datetime.now().isoformat()
    
    # ==================== Interaction Lifecycle ====================
    
    def start_interaction(self, session_id: str, task: str) -> InteractionLog:
        """Start logging a new interaction/task."""
        self._current_interaction = InteractionLog(
            session_id=session_id,
            task=task,
            started_at=self._timestamp(),
        )
        
        self.logger.info(f"=== Starting Task ===")
        self.logger.info(f"Session: {session_id}")
        self.logger.info(f"Task: {self._truncate(task, 200)}")
        
        # Create interaction log file
        if self.log_to_file:
            log_file = self.log_dir / f"interaction_{session_id}.jsonl"
            self._write_log_entry(log_file, {
                "event": "start",
                "timestamp": self._current_interaction.started_at,
                "session_id": session_id,
                "task": task,
            })
        
        return self._current_interaction
    
    def end_interaction(
        self,
        status: str = "completed",
        result: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """End the current interaction."""
        if not self._current_interaction:
            return
        
        self._current_interaction.completed_at = self._timestamp()
        self._current_interaction.status = status
        self._current_interaction.final_result = result
        self._current_interaction.error = error
        
        self.logger.info(f"=== Task {status.upper()} ===")
        if result:
            self.logger.info(f"Result: {self._truncate(result, 200)}")
        if error:
            self.logger.error(f"Error: {error}")
        
        # Write final summary
        if self.log_to_file:
            log_file = self.log_dir / f"interaction_{self._current_interaction.session_id}.jsonl"
            self._write_log_entry(log_file, {
                "event": "end",
                "timestamp": self._current_interaction.completed_at,
                "status": status,
                "result_preview": self._truncate(result) if result else None,
                "error": error,
                "summary": self._current_interaction.summary(),
            })
            
            # Also write complete interaction log
            complete_log = self.log_dir / f"interaction_{self._current_interaction.session_id}_complete.json"
            with open(complete_log, "w") as f:
                json.dump(self._current_interaction.to_dict(), f, indent=2)
        
        interaction = self._current_interaction
        self._current_interaction = None
        return interaction
    
    # ==================== LLM Call Logging ====================
    
    def log_llm_request(
        self,
        model: str,
        messages: List[Dict[str, str]],
    ):
        """Log an LLM request (before sending)."""
        self.logger.debug(f"LLM Request: model={model}, messages={len(messages)}")
        
        # Log message details at debug level
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            self.logger.debug(f"  [{i}] {role}: {self._truncate(content, 100)}")
    
    def log_llm_response(
        self,
        model: str,
        messages: List[Dict[str, str]],
        response: str,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ):
        """Log an LLM response."""
        # Create preview of messages
        if messages:
            first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
            messages_preview = self._truncate(first_user, 200)
        else:
            messages_preview = ""
        
        log_entry = LLMCallLog(
            timestamp=self._timestamp(),
            model=model,
            messages_count=len(messages),
            messages_preview=messages_preview,
            response_preview=self._truncate(response),
            response_length=len(response),
            duration_ms=duration_ms,
            error=error,
        )
        
        if self._current_interaction:
            self._current_interaction.llm_calls.append(log_entry)
        
        if error:
            self.logger.error(f"LLM Error: {error}")
        else:
            self.logger.info(f"LLM Response: {len(response)} chars, {duration_ms:.0f}ms" if duration_ms else f"LLM Response: {len(response)} chars")
            self.logger.debug(f"Response preview: {self._truncate(response, 200)}")
        
        if self.log_to_file and self._current_interaction:
            log_file = self.log_dir / f"interaction_{self._current_interaction.session_id}.jsonl"
            self._write_log_entry(log_file, {
                "event": "llm_call",
                **log_entry.to_dict(),
            })
    
    # ==================== Tool/Action Logging ====================
    
    def log_tool_call(
        self,
        tool: str,
        params: Dict[str, Any],
        result: str,
        success: bool,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ):
        """Log a tool/action execution."""
        # Sanitize params (remove large content)
        safe_params = {}
        for k, v in params.items():
            if k == "content" and isinstance(v, str) and len(v) > 200:
                safe_params[k] = f"[{len(v)} chars]"
            else:
                safe_params[k] = v
        
        log_entry = ToolCallLog(
            timestamp=self._timestamp(),
            tool=tool,
            params=safe_params,
            result_preview=self._truncate(result),
            result_length=len(result),
            success=success,
            duration_ms=duration_ms,
            error=error,
        )
        
        if self._current_interaction:
            self._current_interaction.tool_calls.append(log_entry)
        
        status_icon = "✓" if success else "✗"
        self.logger.info(f"Tool {status_icon} {tool}: {self._truncate(str(safe_params), 100)}")
        if not success and error:
            self.logger.error(f"  Error: {error}")
        else:
            self.logger.debug(f"  Result: {self._truncate(result, 200)}")
        
        if self.log_to_file and self._current_interaction:
            log_file = self.log_dir / f"interaction_{self._current_interaction.session_id}.jsonl"
            self._write_log_entry(log_file, {
                "event": "tool_call",
                **log_entry.to_dict(),
            })
    
    # ==================== Iteration Logging ====================
    
    def log_iteration(
        self,
        iteration: int,
        thought: Optional[str],
        action: Optional[str],
        action_input: Optional[Dict[str, Any]],
        observation: Optional[str],
        is_complete: bool,
    ):
        """Log a ReAct iteration."""
        log_entry = IterationLog(
            timestamp=self._timestamp(),
            iteration=iteration,
            thought=self._truncate(thought) if thought else None,
            action=action,
            action_input=action_input,
            observation_preview=self._truncate(observation) if observation else None,
            is_complete=is_complete,
        )
        
        if self._current_interaction:
            self._current_interaction.iterations.append(log_entry)
        
        self.logger.info(f"--- Iteration {iteration} ---")
        if thought:
            self.logger.info(f"💭 Thought: {self._truncate(thought, 150)}")
        if action:
            self.logger.info(f"🔧 Action: {action}")
            if action_input:
                self.logger.debug(f"   Input: {action_input}")
        if observation:
            self.logger.debug(f"👁 Observation: {self._truncate(observation, 150)}")
        if is_complete:
            self.logger.info(f"✅ Task marked complete")
        
        if self.log_to_file and self._current_interaction:
            log_file = self.log_dir / f"interaction_{self._current_interaction.session_id}.jsonl"
            self._write_log_entry(log_file, {
                "event": "iteration",
                **log_entry.to_dict(),
            })
    
    # ==================== General Logging ====================
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
    
    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
    
    # ==================== File Operations ====================
    
    def _write_log_entry(self, log_file: Path, entry: Dict[str, Any]):
        """Write a log entry to JSONL file."""
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self.logger.error(f"Failed to write log: {e}")
    
    def get_interaction_log(self) -> Optional[InteractionLog]:
        """Get the current interaction log."""
        return self._current_interaction
    
    def list_logs(self) -> List[str]:
        """List available log files."""
        if not self.log_dir.exists():
            return []
        return sorted([f.name for f in self.log_dir.glob("interaction_*.json")])
    
    def load_log(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load a complete interaction log."""
        log_file = self.log_dir / f"interaction_{session_id}_complete.json"
        if log_file.exists():
            with open(log_file, "r") as f:
                return json.load(f)
        return None


# Global logger instance (can be replaced)
_logger: Optional[AgentLogger] = None


def get_logger() -> AgentLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = AgentLogger()
    return _logger


def set_logger(logger: AgentLogger):
    """Set the global logger instance."""
    global _logger
    _logger = logger
