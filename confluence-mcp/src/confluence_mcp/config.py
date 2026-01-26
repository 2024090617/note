"""
Configuration for Confluence MCP Server

Supports both Confluence Cloud and Server/Data Center.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ConfluenceType(str, Enum):
    """Confluence deployment type"""
    CLOUD = "cloud"
    SERVER = "server"  # Also covers Data Center


@dataclass
class ConfluenceConfig:
    """Configuration for Confluence connection"""
    
    # Base URL (e.g., https://company.atlassian.net or https://confluence.company.com)
    base_url: str = field(default_factory=lambda: os.getenv("CONFLUENCE_URL", ""))
    
    # Authentication
    username: str = field(default_factory=lambda: os.getenv("CONFLUENCE_USERNAME", ""))
    api_token: str = field(default_factory=lambda: os.getenv("CONFLUENCE_API_TOKEN", ""))
    
    # For Server/DC with personal access token
    personal_access_token: str = field(
        default_factory=lambda: os.getenv("CONFLUENCE_PAT", "")
    )
    
    # Deployment type
    confluence_type: ConfluenceType = field(
        default_factory=lambda: ConfluenceType(
            os.getenv("CONFLUENCE_TYPE", "cloud").lower()
        )
    )
    
    # Default space key for operations
    default_space: str = field(
        default_factory=lambda: os.getenv("CONFLUENCE_DEFAULT_SPACE", "")
    )
    
    # Request settings
    timeout: float = 30.0
    max_retries: int = 3
    
    # Content settings
    expand_macros: bool = True
    include_attachments: bool = True
    
    @property
    def api_base(self) -> str:
        """Get the API base URL based on deployment type"""
        base = self.base_url.rstrip("/")
        if self.confluence_type == ConfluenceType.CLOUD:
            return f"{base}/wiki/rest/api"
        else:
            return f"{base}/rest/api"
    
    @property
    def api_v2_base(self) -> str:
        """Get API v2 base URL (Cloud only)"""
        base = self.base_url.rstrip("/")
        return f"{base}/wiki/api/v2"
    
    @property
    def auth_headers(self) -> dict:
        """Get authentication headers"""
        import base64
        
        if self.personal_access_token:
            # Personal Access Token (Server/DC)
            return {"Authorization": f"Bearer {self.personal_access_token}"}
        elif self.username and self.api_token:
            # Basic auth with API token (Cloud) or password (Server)
            credentials = base64.b64encode(
                f"{self.username}:{self.api_token}".encode()
            ).decode()
            return {"Authorization": f"Basic {credentials}"}
        else:
            return {}
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        if not self.base_url:
            errors.append("CONFLUENCE_URL is required")
        
        if not self.personal_access_token and not (self.username and self.api_token):
            errors.append(
                "Either CONFLUENCE_PAT or both CONFLUENCE_USERNAME and "
                "CONFLUENCE_API_TOKEN are required"
            )
        
        return errors
    
    @classmethod
    def from_env(cls) -> "ConfluenceConfig":
        """Create configuration from environment variables"""
        from dotenv import load_dotenv
        load_dotenv()
        return cls()
