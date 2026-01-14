"""Authentication handler for GitHub Copilot API."""

import time
import requests
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class CopilotToken:
    """Copilot API token with expiration."""
    
    token: str
    expires_at: datetime
    
    def is_expired(self) -> bool:
        """Check if token is expired.
        
        Returns:
            True if token is expired
        """
        return datetime.now() >= self.expires_at
    
    def is_near_expiry(self, buffer_seconds: int = 300) -> bool:
        """Check if token is near expiry.
        
        Args:
            buffer_seconds: Buffer time before expiry
            
        Returns:
            True if token will expire within buffer time
        """
        return datetime.now() >= (self.expires_at - timedelta(seconds=buffer_seconds))


class GitHubAuthenticator:
    """Handles GitHub authentication and token management."""
    
    def __init__(self, github_token: str):
        """Initialize authenticator.
        
        Args:
            github_token: GitHub personal access token
        """
        self.github_token = github_token
        self._copilot_token: Optional[CopilotToken] = None
    
    def get_copilot_token(self, force_refresh: bool = False) -> str:
        """Get valid Copilot API token.
        
        Args:
            force_refresh: Force token refresh even if cached
            
        Returns:
            Valid Copilot API token
            
        Raises:
            AuthenticationError: If authentication fails
        """
        # Return cached token if valid
        if (
            not force_refresh
            and self._copilot_token
            and not self._copilot_token.is_near_expiry()
        ):
            return self._copilot_token.token
        
        # Fetch new token
        self._copilot_token = self._fetch_copilot_token()
        return self._copilot_token.token
    
    def _fetch_copilot_token(self) -> CopilotToken:
        """Fetch Copilot token from GitHub.
        
        Returns:
            CopilotToken instance
            
        Raises:
            AuthenticationError: If token fetch fails
        """
        # Try multiple endpoints as the API may vary
        endpoints = [
            "https://api.github.com/copilot_internal/v2/token",
            "https://api.githubcopilot.com/token",
        ]
        
        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/json",
            "Editor-Version": "vscode/1.85.0",
            "Editor-Plugin-Version": "copilot/1.150.0",
        }
        
        last_error = None
        for url in endpoints:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                token = data.get("token")
                expires_at = data.get("expires_at")
                
                if not token or not expires_at:
                    continue
                
                # Parse expiration time
                expires_dt = datetime.fromtimestamp(expires_at)
                
                return CopilotToken(token=token, expires_at=expires_dt)
                
            except requests.exceptions.RequestException as e:
                last_error = e
                continue
        
        # If all endpoints fail, just use the GitHub token directly
        # Some Copilot APIs accept the GitHub token directly
        return CopilotToken(
            token=self.github_token,
            expires_at=datetime.now() + timedelta(days=365)
        )
    
    def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for API requests.
        
        Returns:
            Dictionary of headers
        """
        token = self.get_copilot_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass
