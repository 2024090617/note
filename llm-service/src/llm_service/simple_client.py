"""Alternative client using OpenAI-compatible API.

This module provides a simpler approach that can work with:
- OpenAI API directly
- GitHub Copilot (if configured properly)
- Any OpenAI-compatible endpoint
"""

import os
import requests
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class SimpleMessage(BaseModel):
    """Simple message format."""
    role: str
    content: str


class SimpleClient:
    """Simplified LLM client that works with any OpenAI-compatible API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-3.5-turbo"
    ):
        """Initialize simple client.
        
        Args:
            api_key: API key (defaults to GITHUB_TOKEN or OPENAI_API_KEY from env)
            base_url: API base URL
            model: Model name
        """
        self.api_key = api_key or os.getenv("GITHUB_TOKEN") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("No API key provided")
        
        self.base_url = base_url.rstrip("/")
        self.model = model
    
    def query(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> str:
        """Send a simple query.
        
        Args:
            prompt: User prompt
            system: Optional system prompt
            max_tokens: Maximum tokens
            temperature: Sampling temperature
            
        Returns:
            Response text
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        data = response.json()
        return data["choices"][0]["message"]["content"]


def main():
    """Test the simple client."""
    import sys
    
    # Try with GitHub token
    client = SimpleClient()
    
    try:
        response = client.query("Say hello in one word")
        print(f"Success: {response}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
