"""Configuration management for LLM Service."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class Config(BaseModel):
    """Configuration for LLM Service."""
    
    # GitHub Authentication
    github_token: str = Field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN", ""),
        description="GitHub personal access token"
    )
    
    # OpenAI Authentication (alternative)
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""),
        description="OpenAI API key (alternative to GitHub)"
    )
    
    # API Configuration
    api_base_url: str = Field(
        default="https://models.inference.ai.azure.com",
        description="Base URL for LLM API (GitHub Models)"
    )
    
    copilot_api_url: str = Field(
        default="https://api.githubcopilot.com",
        description="Alternative GitHub Copilot API URL"
    )
    
    github_models_url: str = Field(
        default="https://models.inference.ai.azure.com",
        description="GitHub Models API URL (free for GitHub users)"
    )
    
    # Model Configuration
    model: str = Field(
        default="gpt-4o-mini",
        description="Model to use for completions"
    )
    
    max_tokens: int = Field(
        default=4096,
        description="Maximum tokens in response"
    )
    
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature"
    )
    
    # Timeout Configuration
    timeout: int = Field(
        default=60,
        description="Request timeout in seconds"
    )
    
    # Streaming
    stream: bool = Field(
        default=False,
        description="Enable streaming responses"
    )
    
    @classmethod
    def from_env(cls, env_file: Optional[Path] = None) -> "Config":
        """Load configuration from environment variables.
        
        Args:
            env_file: Optional path to .env file
            
        Returns:
            Config instance
        """
        if env_file and env_file.exists():
            load_dotenv(env_file, override=True)
        else:
            # Try default locations
            package_dir = Path(__file__).parent.parent.parent  # Go up to llm-service/
            for path in [
                Path(".env"),  # Current working directory
                package_dir / ".env",  # Package root
                Path.home() / ".llm-service" / ".env"  # User home
            ]:
                if path.exists():
                    load_dotenv(path, override=True)
                    break
        
        return cls()
    
    def validate_auth(self) -> bool:
        """Check if authentication is configured.
        
        Returns:
            True if GitHub token or OpenAI key is set
        """
        return bool(self.github_token or self.openai_api_key)
    
    def get_config_dir(self) -> Path:
        """Get configuration directory.
        
        Returns:
            Path to config directory
        """
        config_dir = Path.home() / ".llm-service"
        config_dir.mkdir(exist_ok=True)
        return config_dir
