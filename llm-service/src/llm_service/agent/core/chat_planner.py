"""Lightweight chat-time planner for safe tool-assisted responses."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from ..copilot_client import ChatMessage
from ..tools.types import ToolResult
from .prompt import CHAT_TOOL_PLANNER_SYSTEM_PROMPT


class ChatToolPlanner:
    """Plans and executes chat-safe tool usage without exposing JSON to users."""

    def __init__(
        self,
        client_getter: Callable[[], Any],
        model_getter: Callable[[], str],
        tools: Any,
        logger: Any,
        json_extractor: Callable[[str], Optional[Dict[str, Any]]],
        allowed_tools: Optional[List[str]] = None,
        max_tool_calls_per_turn: int = 1,
    ):
        self._client_getter = client_getter
        self._model_getter = model_getter
        self._tools = tools
        self._logger = logger
        self._json_extractor = json_extractor
        resolved_allowed_tools = ["read_online_content"] if allowed_tools is None else allowed_tools
        self.allowed_tools = set(resolved_allowed_tools)
        self.max_tool_calls_per_turn = max(0, int(max_tool_calls_per_turn))

    def should_consider(self, user_input: str) -> bool:
        """Cheap gate to avoid planner calls on ordinary conversational turns."""
        text = user_input.strip().lower()
        has_url = "http://" in text or "https://" in text
        asks_fetch = any(
            k in text for k in ("read this page", "fetch", "summarize", "open url", "web page")
        )
        return has_url or asks_fetch

    def plan(self, user_input: str, focus_mode: str, active_goal: str = "") -> Dict[str, Any]:
        """Plan chat-time tool usage without exposing tool JSON to the user."""
        if self.max_tool_calls_per_turn <= 0:
            return {"use_tool": False, "tool": "none", "arguments": {}, "reason": "planner disabled by policy"}

        if not self.should_consider(user_input):
            return {"use_tool": False, "tool": "none", "arguments": {}, "reason": "not needed"}

        payload = {
            "user_input": user_input,
            "focus_mode": focus_mode,
            "active_goal": active_goal,
            "allowed_tools": sorted(self.allowed_tools),
        }
        messages = [
            ChatMessage(role="system", content=CHAT_TOOL_PLANNER_SYSTEM_PROMPT),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ]

        try:
            response = self._client_getter().chat(messages, model=self._model_getter())
            data = self._json_extractor(response.content) or {}
        except Exception:
            data = {}

        use_tool = bool(data.get("use_tool", False))
        tool = str(data.get("tool", "none") or "none")
        arguments = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}

        if tool not in self.allowed_tools:
            return {"use_tool": False, "tool": "none", "arguments": {}, "reason": "unsupported tool"}

        if tool != "read_online_content":
            return {"use_tool": False, "tool": "none", "arguments": {}, "reason": "tool not implemented"}

        if not use_tool:
            return {
                "use_tool": False,
                "tool": "none",
                "arguments": {},
                "reason": str(data.get("reason", "not needed")),
            }

        url = str(arguments.get("url", "")).strip()
        if not url:
            m = re.search(r"https?://\S+", user_input)
            if m:
                url = m.group(0).rstrip(").,;!]")
        if not url:
            return {"use_tool": False, "tool": "none", "arguments": {}, "reason": "missing url"}

        return {
            "use_tool": True,
            "tool": "read_online_content",
            "arguments": {"url": url},
            "reason": str(data.get("reason", "requested web fetch")),
        }

    def execute(self, planner_decision: Dict[str, Any]) -> Optional[ToolResult]:
        """Execute a single chat-safe planned tool call."""
        tool = str(planner_decision.get("tool", "none"))
        args = planner_decision.get("arguments") or {}
        if tool not in self.allowed_tools:
            return None

        if tool != "read_online_content":
            return None

        result = self._tools.read_online_content(str(args.get("url", "")))
        self._logger.log_tool_call(
            tool=tool,
            params={"url": str(args.get("url", ""))},
            result=result.output if result.success else "",
            success=result.success,
            duration_ms=None,
            error=result.error if not result.success else None,
        )
        return result

    def render_tool_note(self, planner_decision: Dict[str, Any], tool_result: ToolResult, max_chars: int) -> str:
        """Render tool output/error as internal system context for final chat response."""
        tool_name = str(planner_decision.get("tool", ""))
        if tool_result.success:
            return (
                "Tool result for this user turn (use it if relevant):\n"
                f"<tool_result tool=\"{tool_name}\">\n"
                f"{tool_result.output[:max_chars]}\n"
                "</tool_result>"
            )

        return (
            "Tool call failed for this user turn; explain briefly and provide next steps.\n"
            f"<tool_error tool=\"{tool_name}\">\n"
            f"{tool_result.error or 'unknown error'}\n"
            "</tool_error>"
        )
