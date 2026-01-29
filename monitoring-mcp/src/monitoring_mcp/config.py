"""
Configuration management for Monitoring MCP Server.

Uses pydantic-settings for environment variable loading with JSON config support.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Base configuration for a monitoring service."""
    
    enabled: bool = Field(default=True, description="Whether this service is enabled")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    retry_count: int = Field(default=3, description="Number of retries on failure")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")


class SplunkConfig(ServiceConfig):
    """Splunk service configuration."""
    
    model_config = SettingsConfigDict(env_prefix="SPLUNK_")
    
    base_url: str = Field(default="", description="Splunk REST API base URL")
    token: str = Field(default="", description="Splunk HEC token")
    username: Optional[str] = Field(default=None, description="Splunk username (alternative to token)")
    password: Optional[str] = Field(default=None, description="Splunk password")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")
    
    @property
    def is_configured(self) -> bool:
        """Check if Splunk is properly configured."""
        return bool(self.base_url and (self.token or (self.username and self.password)))


class AppDynamicsConfig(ServiceConfig):
    """AppDynamics service configuration."""
    
    model_config = SettingsConfigDict(env_prefix="APPDYNAMICS_")
    
    base_url: str = Field(default="", description="AppDynamics controller URL")
    account_name: str = Field(default="", description="Account name")
    api_client_name: str = Field(default="", description="API client name for OAuth")
    api_client_secret: str = Field(default="", description="API client secret")
    token_url: Optional[str] = Field(default=None, description="OAuth token endpoint")
    
    @property
    def is_configured(self) -> bool:
        """Check if AppDynamics is properly configured."""
        return bool(self.base_url and self.api_client_name and self.api_client_secret)
    
    def get_token_url(self) -> str:
        """Get OAuth token URL."""
        if self.token_url:
            return self.token_url
        return f"{self.base_url}/controller/api/oauth/access_token"


class KafkaConfig(ServiceConfig):
    """Kafka service configuration."""
    
    model_config = SettingsConfigDict(env_prefix="KAFKA_")
    
    bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers")
    sasl_mechanism: Optional[str] = Field(default=None, description="SASL mechanism (PLAIN, SCRAM-SHA-256, etc.)")
    sasl_username: Optional[str] = Field(default=None, description="SASL username")
    sasl_password: Optional[str] = Field(default=None, description="SASL password")
    ssl_enabled: bool = Field(default=False, description="Enable SSL")
    ssl_cafile: Optional[str] = Field(default=None, description="SSL CA file path")
    ssl_certfile: Optional[str] = Field(default=None, description="SSL certificate file path")
    ssl_keyfile: Optional[str] = Field(default=None, description="SSL key file path")
    
    @property
    def is_configured(self) -> bool:
        """Check if Kafka is properly configured."""
        return bool(self.bootstrap_servers)
    
    @property
    def bootstrap_servers_list(self) -> List[str]:
        """Get bootstrap servers as a list."""
        return [s.strip() for s in self.bootstrap_servers.split(",")]


class MongoDBConfig(ServiceConfig):
    """MongoDB service configuration."""
    
    model_config = SettingsConfigDict(env_prefix="MONGODB_")
    
    uri: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    database: str = Field(default="admin", description="Default database for status commands")
    
    @property
    def is_configured(self) -> bool:
        """Check if MongoDB is properly configured."""
        return bool(self.uri)


class ThresholdConfig(BaseSettings):
    """Threshold configuration for health checks."""
    
    model_config = SettingsConfigDict(env_prefix="THRESHOLD_")
    
    # Kafka thresholds
    kafka_lag_warning: int = Field(default=100, description="Kafka lag warning threshold")
    kafka_lag_critical: int = Field(default=1000, description="Kafka lag critical threshold")
    
    # Error rate thresholds (as percentage, e.g., 1.0 = 1%)
    error_rate_warning: float = Field(default=1.0, description="Error rate warning threshold (%)")
    error_rate_critical: float = Field(default=5.0, description="Error rate critical threshold (%)")
    
    # Response time thresholds (milliseconds)
    response_time_warning: int = Field(default=1000, description="Response time warning (ms)")
    response_time_critical: int = Field(default=5000, description="Response time critical (ms)")
    
    # JVM thresholds
    jvm_heap_usage_warning: float = Field(default=80.0, description="JVM heap usage warning (%)")
    jvm_heap_usage_critical: float = Field(default=95.0, description="JVM heap usage critical (%)")
    
    # MongoDB thresholds
    mongodb_connections_warning: int = Field(default=1000, description="MongoDB connections warning")
    mongodb_connections_critical: int = Field(default=5000, description="MongoDB connections critical")
    mongodb_replication_lag_warning: int = Field(default=10, description="Replication lag warning (seconds)")
    mongodb_replication_lag_critical: int = Field(default=60, description="Replication lag critical (seconds)")


class MonitoringConfig(BaseSettings):
    """Main configuration for Monitoring MCP Server."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Service configurations
    splunk: SplunkConfig = Field(default_factory=SplunkConfig)
    appdynamics: AppDynamicsConfig = Field(default_factory=AppDynamicsConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    mongodb: MongoDBConfig = Field(default_factory=MongoDBConfig)
    
    # Thresholds
    thresholds: ThresholdConfig = Field(default_factory=ThresholdConfig)
    
    # General settings
    debug: bool = Field(default=False, description="Enable debug logging")
    request_timeout: int = Field(default=30, description="Default request timeout")
    
    @classmethod
    def load_from_file(cls, config_path: Path) -> "MonitoringConfig":
        """Load configuration from JSON file with env var overrides."""
        config_data = {}
        
        if config_path.exists():
            with open(config_path) as f:
                config_data = json.load(f)
        
        return cls(**config_data)
    
    def get_enabled_services(self) -> List[str]:
        """Get list of enabled and configured services."""
        services = []
        
        if self.splunk.enabled and self.splunk.is_configured:
            services.append("splunk")
        if self.appdynamics.enabled and self.appdynamics.is_configured:
            services.append("appdynamics")
        if self.kafka.enabled and self.kafka.is_configured:
            services.append("kafka")
        if self.mongodb.enabled and self.mongodb.is_configured:
            services.append("mongodb")
        
        return services
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (masking secrets)."""
        return {
            "splunk": {
                "enabled": self.splunk.enabled,
                "base_url": self.splunk.base_url,
                "configured": self.splunk.is_configured,
            },
            "appdynamics": {
                "enabled": self.appdynamics.enabled,
                "base_url": self.appdynamics.base_url,
                "configured": self.appdynamics.is_configured,
            },
            "kafka": {
                "enabled": self.kafka.enabled,
                "bootstrap_servers": self.kafka.bootstrap_servers,
                "configured": self.kafka.is_configured,
            },
            "mongodb": {
                "enabled": self.mongodb.enabled,
                "configured": self.mongodb.is_configured,
            },
            "thresholds": self.thresholds.model_dump(),
            "enabled_services": self.get_enabled_services(),
        }


# Global config instance (lazy loaded)
_config: Optional[MonitoringConfig] = None


def get_config() -> MonitoringConfig:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = MonitoringConfig()
    return _config


def reload_config() -> MonitoringConfig:
    """Reload configuration from environment."""
    global _config
    _config = MonitoringConfig()
    return _config
