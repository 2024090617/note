"""
Copilot Bridge Client - HTTP client for VS Code Copilot Language Model API.

Connects to the Copilot Bridge server running in VS Code at http://127.0.0.1:19823
"""

import requests
from typing import List, Dict, Any, Optional, Iterator
from dataclasses import dataclass, field
from enum import Enum
import json


class ModelFamily(str, Enum):
    """Available Copilot model families."""
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4 = "gpt-4"
    GPT_35_TURBO = "gpt-3.5-turbo"
    CLAUDE_SONNET = "claude-3.5-sonnet"
    O1 = "o1"
    O1_MINI = "o1-mini"
    O3_MINI = "o3-mini"


@dataclass
class CopilotModel:
    """Copilot model information."""
    id: str
    name: str
    vendor: str
    family: str
    version: str
    max_input_tokens: int


@dataclass 
class ChatMessage:
    """Chat message for Copilot API."""
    role: str  # "system", "user", "assistant"
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatResponse:
    """Response from Copilot chat completion."""
    content: str
    model: str
    finish_reason: str = "stop"
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "ChatResponse":
        """Parse API response."""
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices in response")
        
        choice = choices[0]
        message = choice.get("message", {})
        
        return cls(
            content=message.get("content", ""),
            model=data.get("model", "unknown"),
            finish_reason=choice.get("finish_reason", "stop")
        )


class CopilotBridgeError(Exception):
    """Error communicating with Copilot Bridge."""
    pass


class CopilotBridgeClient:
    """
    HTTP client for the Copilot Bridge server.
    
    The bridge runs as a VS Code extension and exposes Copilot models via HTTP.
    Default endpoint: http://127.0.0.1:19823
    """
    
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 19823
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        model: str = "gpt-4o-mini",
        timeout: int = 120,
    ):
        """
        Initialize Copilot Bridge client.
        
        Args:
            host: Bridge server host
            port: Bridge server port
            model: Default model family to use
            timeout: Request timeout in seconds
        """
        self.base_url = f"http://{host}:{port}"
        self.model = model
        self.timeout = timeout
        self._available_models: Optional[List[CopilotModel]] = None
    
    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/chat"
    
    @property
    def models_url(self) -> str:
        return f"{self.base_url}/models"
    
    def is_available(self) -> bool:
        """Check if Copilot Bridge server is running."""
        try:
            response = requests.get(self.models_url, timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def get_models(self, refresh: bool = False) -> List[CopilotModel]:
        """
        Get available Copilot models.
        
        Args:
            refresh: Force refresh the model list
            
        Returns:
            List of available models
            
        Raises:
            CopilotBridgeError: If bridge is not available
        """
        if self._available_models is not None and not refresh:
            return self._available_models
        
        try:
            response = requests.get(self.models_url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            self._available_models = [
                CopilotModel(
                    id=m.get("id", ""),
                    name=m.get("name", ""),
                    vendor=m.get("vendor", "copilot"),
                    family=m.get("family", ""),
                    version=m.get("version", ""),
                    max_input_tokens=m.get("maxInputTokens", 0)
                )
                for m in data
            ]
            return self._available_models
            
        except requests.ConnectionError:
            raise CopilotBridgeError(
                f"Cannot connect to Copilot Bridge at {self.base_url}. "
                "Make sure VS Code is running with the Copilot Bridge extension "
                "and run command 'Start Copilot Bridge Server'."
            )
        except requests.RequestException as e:
            raise CopilotBridgeError(f"Failed to get models: {e}")
    
    def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
    ) -> ChatResponse:
        """
        Send chat completion request.
        
        Args:
            messages: List of chat messages
            model: Model family to use (overrides default)
            
        Returns:
            ChatResponse with completion
            
        Raises:
            CopilotBridgeError: If request fails
        """
        payload = {
            "model": model or self.model,
            "messages": [m.to_dict() for m in messages],
        }
        
        try:
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=self.timeout,
            )
            
            if response.status_code == 404:
                data = response.json()
                raise CopilotBridgeError(
                    f"Model not found: {data.get('error', 'Unknown model')}"
                )
            
            response.raise_for_status()
            return ChatResponse.from_api_response(response.json())
            
        except requests.ConnectionError:
            raise CopilotBridgeError(
                f"Cannot connect to Copilot Bridge at {self.base_url}. "
                "Ensure the bridge server is running."
            )
        except requests.Timeout:
            raise CopilotBridgeError(
                f"Request timed out after {self.timeout}s. "
                "The model may be processing a complex request."
            )
        except requests.RequestException as e:
            raise CopilotBridgeError(f"Chat request failed: {e}")
    
    def simple_query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Send a simple query and get response text.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            model: Model family to use
            
        Returns:
            Response text
        """
        messages = []
        
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        
        messages.append(ChatMessage(role="user", content=prompt))
        
        response = self.chat(messages, model=model)
        return response.content
    
    def __repr__(self) -> str:
        return f"CopilotBridgeClient(url={self.base_url}, model={self.model})"
