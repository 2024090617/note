"""
Authentication providers for monitoring services.

Unified abstraction for different authentication mechanisms:
- Token-based (Splunk HEC)
- OAuth 2.0 (AppDynamics)
- SASL (Kafka)
- Connection string (MongoDB)
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx

from monitoring_mcp.config import (
    AppDynamicsConfig,
    KafkaConfig,
    MongoDBConfig,
    SplunkConfig,
    get_config,
)

logger = logging.getLogger(__name__)


class AuthProvider(ABC):
    """Abstract base class for authentication providers."""
    
    @abstractmethod
    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for HTTP requests."""
        pass
    
    @abstractmethod
    async def get_credentials(self) -> Dict[str, Any]:
        """Get credentials for non-HTTP authentication (Kafka, MongoDB)."""
        pass
    
    @abstractmethod
    def is_valid(self) -> bool:
        """Check if authentication is valid/not expired."""
        pass
    
    async def refresh(self) -> None:
        """Refresh authentication if needed (e.g., OAuth token refresh)."""
        pass


class SplunkAuthProvider(AuthProvider):
    """Splunk authentication using HEC token or basic auth."""
    
    def __init__(self, config: SplunkConfig):
        self.config = config
    
    async def get_headers(self) -> Dict[str, str]:
        """Get Splunk authentication headers."""
        if self.config.token:
            return {
                "Authorization": f"Bearer {self.config.token}",
                "Content-Type": "application/json",
            }
        elif self.config.username and self.config.password:
            import base64
            credentials = base64.b64encode(
                f"{self.config.username}:{self.config.password}".encode()
            ).decode()
            return {
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/json",
            }
        else:
            raise ValueError("Splunk authentication not configured")
    
    async def get_credentials(self) -> Dict[str, Any]:
        """Return headers as credentials for Splunk."""
        return await self.get_headers()
    
    def is_valid(self) -> bool:
        """Token-based auth is always valid until rejected by server."""
        return self.config.is_configured


class AppDynamicsAuthProvider(AuthProvider):
    """AppDynamics OAuth 2.0 authentication."""
    
    def __init__(self, config: AppDynamicsConfig):
        self.config = config
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()
    
    async def _fetch_token(self) -> None:
        """Fetch new OAuth token from AppDynamics."""
        logger.info("Fetching new AppDynamics OAuth token")
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.config.get_token_url(),
                data={
                    "grant_type": "client_credentials",
                    "client_id": f"{self.config.api_client_name}@{self.config.account_name}",
                    "client_secret": self.config.api_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            
            data = response.json()
            self._access_token = data["access_token"]
            # Token typically expires in 5 minutes, refresh 1 minute early
            expires_in = data.get("expires_in", 300)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
            
            logger.info(f"AppDynamics token acquired, expires in {expires_in}s")
    
    async def get_headers(self) -> Dict[str, str]:
        """Get AppDynamics authentication headers with auto-refresh."""
        async with self._lock:
            if not self.is_valid():
                await self._fetch_token()
        
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
    
    async def get_credentials(self) -> Dict[str, Any]:
        """Return access token as credentials."""
        headers = await self.get_headers()
        return {"access_token": self._access_token, "headers": headers}
    
    def is_valid(self) -> bool:
        """Check if token exists and is not expired."""
        if not self._access_token or not self._token_expires_at:
            return False
        return datetime.now() < self._token_expires_at
    
    async def refresh(self) -> None:
        """Force token refresh."""
        async with self._lock:
            await self._fetch_token()


class KafkaAuthProvider(AuthProvider):
    """Kafka SASL/SSL authentication."""
    
    def __init__(self, config: KafkaConfig):
        self.config = config
    
    async def get_headers(self) -> Dict[str, str]:
        """Kafka doesn't use HTTP headers."""
        return {}
    
    async def get_credentials(self) -> Dict[str, Any]:
        """Get Kafka connection credentials."""
        creds: Dict[str, Any] = {
            "bootstrap_servers": self.config.bootstrap_servers_list,
        }
        
        # SASL configuration
        if self.config.sasl_mechanism and self.config.sasl_username:
            creds["sasl_mechanism"] = self.config.sasl_mechanism
            creds["sasl_plain_username"] = self.config.sasl_username
            creds["sasl_plain_password"] = self.config.sasl_password
            creds["security_protocol"] = "SASL_SSL" if self.config.ssl_enabled else "SASL_PLAINTEXT"
        
        # SSL configuration
        if self.config.ssl_enabled:
            if not self.config.sasl_mechanism:
                creds["security_protocol"] = "SSL"
            if self.config.ssl_cafile:
                creds["ssl_cafile"] = self.config.ssl_cafile
            if self.config.ssl_certfile:
                creds["ssl_certfile"] = self.config.ssl_certfile
            if self.config.ssl_keyfile:
                creds["ssl_keyfile"] = self.config.ssl_keyfile
        
        return creds
    
    def is_valid(self) -> bool:
        """Check if Kafka is configured."""
        return self.config.is_configured


class MongoDBAuthProvider(AuthProvider):
    """MongoDB connection string authentication."""
    
    def __init__(self, config: MongoDBConfig):
        self.config = config
    
    async def get_headers(self) -> Dict[str, str]:
        """MongoDB doesn't use HTTP headers."""
        return {}
    
    async def get_credentials(self) -> Dict[str, Any]:
        """Get MongoDB connection credentials."""
        return {
            "uri": self.config.uri,
            "database": self.config.database,
        }
    
    def is_valid(self) -> bool:
        """Check if MongoDB is configured."""
        return self.config.is_configured


# Auth provider registry
_auth_providers: Dict[str, AuthProvider] = {}


def get_auth_provider(service: str) -> AuthProvider:
    """
    Get or create an authentication provider for a service.
    
    Args:
        service: Service name ("splunk", "appdynamics", "kafka", "mongodb")
        
    Returns:
        AuthProvider instance
        
    Raises:
        ValueError: If service is unknown
    """
    if service in _auth_providers:
        return _auth_providers[service]
    
    config = get_config()
    
    if service == "splunk":
        provider = SplunkAuthProvider(config.splunk)
    elif service == "appdynamics":
        provider = AppDynamicsAuthProvider(config.appdynamics)
    elif service == "kafka":
        provider = KafkaAuthProvider(config.kafka)
    elif service == "mongodb":
        provider = MongoDBAuthProvider(config.mongodb)
    else:
        raise ValueError(f"Unknown service: {service}")
    
    _auth_providers[service] = provider
    return provider


def clear_auth_providers() -> None:
    """Clear cached auth providers (useful for testing)."""
    global _auth_providers
    _auth_providers = {}
