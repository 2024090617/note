"""Core LLM client for GitHub Copilot API."""

import json
import requests
from typing import List, Optional, Dict, Any, Iterator
from pydantic import BaseModel, Field
from enum import Enum

from .auth import GitHubAuthenticator, AuthenticationError
from .config import Config


class MessageRole(str, Enum):
    """Message role in conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """Chat message."""
    role: MessageRole
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to API format.
        
        Returns:
            Dictionary representation
        """
        return {
            "role": self.role.value,
            "content": self.content
        }


class ChatResponse(BaseModel):
    """Response from chat completion."""
    content: str
    model: str
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None  # Changed from Dict[str, int] to allow nested structures
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "ChatResponse":
        """Parse API response.
        
        Args:
            data: API response data
            
        Returns:
            ChatResponse instance
        """
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices in response")
        
        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        
        return cls(
            content=content,
            model=data.get("model", "unknown"),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage")
        )


class LLMClient:
    """Client for GitHub Copilot LLM API."""
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize LLM client.
        
        Args:
            config: Optional configuration (loads from env if not provided)
            
        Raises:
            ValueError: If GitHub token is not configured
        """
        self.config = config or Config.from_env()
        
        if not self.config.validate_auth():
            raise ValueError(
                "No API key configured. Set GITHUB_TOKEN or OPENAI_API_KEY environment variable"
            )
        
        # Use GitHub token if available, otherwise OpenAI key
        auth_token = self.config.github_token or self.config.openai_api_key
        self.auth = GitHubAuthenticator(auth_token)
        self.use_openai = bool(self.config.openai_api_key and not self.config.github_token)
    
    def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        stream: bool = False,
    ) -> ChatResponse:
        """Send chat completion request.
        
        Args:
            messages: List of conversation messages
            model: Model to use (overrides config)
            max_tokens: Max tokens in response (overrides config)
            temperature: Sampling temperature (overrides config)
            stream: Enable streaming (overrides config)
            
        Returns:
            ChatResponse with completion
            
        Raises:
            APIError: If API request fails
        """
        # Try multiple API endpoints
        urls = []
        
        # If using OpenAI key, prioritize OpenAI endpoint
        if self.use_openai:
            urls = [
                f"{self.config.api_base_url}/chat/completions",
            ]
        else:
            # For GitHub tokens, try GitHub Models (free) first
            urls = [
                f"{self.config.github_models_url}/chat/completions",
                f"{self.config.copilot_api_url}/chat/completions",
            ]
        
        payload = {
            "model": model or self.config.model,
            "messages": [msg.to_dict() for msg in messages],
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature if temperature is not None else self.config.temperature,
            "stream": stream,
        }
        
        last_error = None
        errors = []  # Track all errors for debugging
        
        for url in urls:
            try:
                headers = self.auth.get_headers()
                # Add additional headers based on endpoint
                if "githubcopilot.com" in url:
                    headers.update({
                        "Editor-Version": "vscode/1.85.0",
                        "Editor-Plugin-Version": "copilot/1.150.0",
                        "OpenAI-Organization": "github-copilot",
                    })
                elif "inference.ai.azure.com" in url:
                    # GitHub Models uses different auth format
                    headers = {
                        "Authorization": f"Bearer {self.config.github_token or self.config.openai_api_key}",
                        "Content-Type": "application/json",
                    }
                
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout,
                    stream=stream,
                )
                response.raise_for_status()
                
                if stream:
                    # TODO: Implement streaming
                    raise NotImplementedError("Streaming not yet implemented")
                
                data = response.json()
                return ChatResponse.from_api_response(data)
                
            except requests.exceptions.RequestException as e:
                last_error = e
                errors.append(f"{url}: {str(e)[:100]}")
                continue
            except (ValueError, KeyError) as e:
                last_error = e
                errors.append(f"{url}: Parse error - {str(e)[:100]}")
                continue
        
        # All attempts failed - show better error message
        if errors:
            error_details = "; ".join(errors)
            raise APIError(f"All endpoints failed: {error_details}")
        
        # All attempts failed - show better error message
        if errors:
            error_details = "; ".join(errors)
            raise APIError(f"All endpoints failed: {error_details}")
        else:
            raise APIError(f"API request failed on all endpoints. Last error: {last_error}")
    
    def simple_query(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Simple query interface.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional arguments passed to chat()
            
        Returns:
            Response content as string
        """
        messages = []
        
        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))
        
        messages.append(Message(role=MessageRole.USER, content=prompt))
        
        response = self.chat(messages, **kwargs)
        return response.content
    
    def continue_conversation(
        self,
        conversation: List[Message],
        user_message: str,
        **kwargs
    ) -> tuple[str, List[Message]]:
        """Continue an existing conversation.
        
        Args:
            conversation: Existing conversation messages
            user_message: New user message
            **kwargs: Additional arguments passed to chat()
            
        Returns:
            Tuple of (response_content, updated_conversation)
        """
        # Add user message
        messages = conversation + [Message(role=MessageRole.USER, content=user_message)]
        
        # Get response
        response = self.chat(messages, **kwargs)
        
        # Add assistant response
        messages.append(Message(role=MessageRole.ASSISTANT, content=response.content))
        
        return response.content, messages


class APIError(Exception):
    """Raised when API request fails."""
    pass
