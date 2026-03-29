"""OpenAI-compatible LLM client.

Works with any server that speaks the OpenAI chat-completions API:
OpenRouter, Ollama, vLLM, LM Studio, etc.
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


class OpenAICompatError(Exception):
    """Error communicating with the OpenAI-compatible endpoint."""


class OpenAICompatClient(LLMClient):
    """Client for any OpenAI-compatible chat-completions endpoint."""

    def __init__(
        self,
        api_base: str = "http://localhost:11434/v1",
        api_key: str = "",
        model: str = "llama3",
        timeout: int = 120,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _headers(self) -> dict:
        h: dict = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

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
            logger.debug("[OpenAICompat] REQUEST:\n%s", json.dumps(payload, indent=2, ensure_ascii=False))
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.api_base}/chat/completions",
                    json=payload,
                    headers=self._headers(),
                )
            if DEBUG_LLM:
                logger.debug("[OpenAICompat] RESPONSE status=%s body=%s", resp.status_code, resp.text[:4000])
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise OpenAICompatError("No choices in response")
            msg = choices[0].get("message", {})
            return ChatResponse(
                content=msg.get("content", ""),
                model=data.get("model", model or self.model),
                finish_reason=choices[0].get("finish_reason", "stop"),
            )

        except httpx.ConnectError:
            raise OpenAICompatError(
                f"Cannot connect to {self.api_base}. Is the server running?"
            )
        except httpx.TimeoutException:
            raise OpenAICompatError(
                f"Request timed out after {self.timeout}s."
            )
        except httpx.HTTPStatusError as e:
            raise OpenAICompatError(f"HTTP error: {e}")

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=3) as client:
                resp = client.get(f"{self.api_base}/models", headers=self._headers())
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def get_models(self) -> List[str]:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(f"{self.api_base}/models", headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return [m.get("id", "") for m in data.get("data", [])]
        except httpx.HTTPError as e:
            raise OpenAICompatError(f"Failed to list models: {e}")

    def __repr__(self) -> str:
        return f"OpenAICompatClient(api_base={self.api_base}, model={self.model})"
