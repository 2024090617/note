"""
Configuration for GitHub MCP Server.

Reads from environment variables (or .env file).
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubConfig(BaseSettings):
    """GitHub MCP server configuration."""

    model_config = SettingsConfigDict(
        env_prefix="GITHUB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    token: str = Field(default="", description="GitHub personal access token")
    api_url: str = Field(
        default="https://api.github.com",
        description="GitHub API base URL (change for GitHub Enterprise)",
    )
    clone_dir: Path = Field(
        default=Path.home() / "github-repos",
        description="Directory for cloned repositories",
    )
    timeout: int = Field(default=30, description="HTTP request timeout in seconds")
    max_download_size: int = Field(
        default=500 * 1024 * 1024,
        description="Maximum download size in bytes (default 500 MB)",
    )


_config: Optional[GitHubConfig] = None


def get_config() -> GitHubConfig:
    """Return the singleton config instance."""
    global _config
    if _config is None:
        _config = GitHubConfig()
    return _config
