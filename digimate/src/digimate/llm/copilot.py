"""Copilot Bridge LLM client.

Connects to the VS Code Copilot Bridge extension at http://127.0.0.1:19823.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

import httpx

from digimate.core.types import ChatMessage, ChatResponse
from digimate.llm.base import LLMClient

logger = logging.getLogger(__name__)

# Hardcoded debug flag — set to True to log full LLM request/response
DEBUG_LLM = True


class CopilotBridgeError(Exception):
    """Error communicating with Copilot Bridge."""


class CopilotBridgeClient(LLMClient):
    """HTTP client for the Copilot Bridge server running in VS Code."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 19823,
        model: str = "claude-haiku-4.5",
        timeout: int = 120,
    ) -> None:
        self.base_url = f"http://{host}:{port}"
        self.model = model
        self.timeout = timeout

    # ── LLMClient interface ──────────────────────────────────────────

    def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
    ) -> ChatResponse:
        payload = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
        }
        if DEBUG_LLM:
            logger.debug("[CopilotBridge] REQUEST:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(f"{self.base_url}/chat", json=payload)

            if DEBUG_LLM:
                logger.debug("[CopilotBridge] RESPONSE status=%s body=%s", resp.status_code, resp.text[:4000])

            if resp.status_code == 404:
                data = resp.json()
                raise CopilotBridgeError(f"Model not found: {data.get('error', '')}")

            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise CopilotBridgeError("No choices in response")
            msg = choices[0].get("message", {})
            return ChatResponse(
                content=msg.get("content", ""),
                model=data.get("model", model or self.model),
                finish_reason=choices[0].get("finish_reason", "stop"),
            )

        except httpx.ConnectError:
            raise CopilotBridgeError(
                f"Cannot connect to Copilot Bridge at {self.base_url}. "
                "Ensure VS Code is running with the Copilot Bridge extension."
            )
        except httpx.TimeoutException:
            raise CopilotBridgeError(
                f"Request timed out after {self.timeout}s."
            )
        except httpx.HTTPStatusError as e:
            raise CopilotBridgeError(f"HTTP error: {e}")

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3) as client:
                resp = client.get(f"{self.base_url}/models")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def get_models(self) -> List[str]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.base_url}/models")
            resp.raise_for_status()
            return [m.get("family", m.get("id", "")) for m in resp.json()]
        except httpx.HTTPError as e:
            raise CopilotBridgeError(f"Failed to get models: {e}")

    def __repr__(self) -> str:
        return f"CopilotBridgeClient(url={self.base_url}, model={self.model})"
