"""
Configuration for the Monitoring Agent.

Loads settings from .env and JSON config files.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ThresholdRule(BaseModel):
    """Threshold rule for a specific metric."""
    
    metric_name: str = Field(..., description="Metric name (e.g., 'kafka_lag', 'error_rate')")
    warning: float = Field(..., description="Warning threshold")
    critical: float = Field(..., description="Critical threshold")
    comparison: str = Field(default="gt", description="Comparison operator: gt, lt, eq, gte, lte")
    enabled: bool = Field(default=True, description="Whether this rule is active")


class ServiceCheck(BaseModel):
    """Configuration for a service health check."""
    
    name: str = Field(..., description="Unique check name")
    service: str = Field(..., description="Service type: splunk, appdynamics, kafka, mongodb")
    tool: str = Field(..., description="MCP tool to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    interval_seconds: int = Field(default=60, description="Check interval")
    enabled: bool = Field(default=True, description="Whether this check is active")
    thresholds: List[ThresholdRule] = Field(default_factory=list, description="Threshold rules")


class TeamsConfig(BaseModel):
    """Microsoft Teams notification configuration."""
    
    webhook_url: str = Field(default="", description="Teams incoming webhook URL")
    enabled: bool = Field(default=True, description="Enable Teams notifications")
    min_severity: str = Field(default="warning", description="Minimum severity to notify: info, warning, critical")
    rate_limit_seconds: int = Field(default=300, description="Minimum seconds between duplicate alerts")
    mention_on_critical: bool = Field(default=True, description="@mention channel on critical alerts")


class DatabaseConfig(BaseModel):
    """Database configuration for metrics storage."""
    
    # SQLite settings
    sqlite_path: str = Field(default="~/.llm-service/monitoring.db", description="SQLite database path")
    
    # Future PostgreSQL settings
    postgres_uri: Optional[str] = Field(default=None, description="PostgreSQL connection URI")
    use_postgres: bool = Field(default=False, description="Use PostgreSQL instead of SQLite")
    
    # Retention settings
    retention_days: int = Field(default=30, description="Days to retain metrics")
    auto_cleanup: bool = Field(default=True, description="Auto-cleanup old records")
    
    @property
    def resolved_path(self) -> Path:
        """Get resolved SQLite path with expanded ~."""
        return Path(self.sqlite_path).expanduser()


class MCPConfig(BaseModel):
    """MCP server connection configuration."""
    
    # For subprocess-based MCP
    command: str = Field(default="monitoring-mcp", description="MCP server command")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    
    # For HTTP-based MCP (future)
    http_endpoint: Optional[str] = Field(default=None, description="HTTP MCP endpoint")
    
    # Connection settings
    timeout_seconds: int = Field(default=30, description="MCP call timeout")
    retry_count: int = Field(default=3, description="Retry count on failure")


class MonitoringAgentConfig(BaseSettings):
    """Main configuration for the Monitoring Agent."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MONITOR_",
        extra="ignore",
    )
    
    # Polling settings
    poll_interval_seconds: int = Field(default=60, description="Default polling interval")
    parallel_checks: bool = Field(default=True, description="Run checks in parallel")
    max_concurrent_checks: int = Field(default=5, description="Max concurrent check operations")
    
    # Service checks (loaded from JSON)
    checks: List[ServiceCheck] = Field(default_factory=list, description="Service checks")
    
    # Global thresholds (can be overridden per-check)
    default_thresholds: Dict[str, ThresholdRule] = Field(
        default_factory=lambda: {
            "kafka_lag": ThresholdRule(metric_name="kafka_lag", warning=100, critical=1000),
            "error_rate": ThresholdRule(metric_name="error_rate", warning=1.0, critical=5.0),
            "response_time": ThresholdRule(metric_name="response_time", warning=1000, critical=5000),
            "jvm_heap": ThresholdRule(metric_name="jvm_heap", warning=80.0, critical=95.0),
            "mongodb_connections": ThresholdRule(metric_name="mongodb_connections", warning=1000, critical=5000),
        },
        description="Default threshold rules",
    )
    
    # Sub-configs
    teams: TeamsConfig = Field(default_factory=TeamsConfig, description="Teams notification config")
    database: DatabaseConfig = Field(default_factory=DatabaseConfig, description="Database config")
    mcp: MCPConfig = Field(default_factory=MCPConfig, description="MCP server config")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_file: Optional[str] = Field(default=None, description="Log file path")
    
    @classmethod
    def load_from_file(cls, config_path: Path) -> "MonitoringAgentConfig":
        """Load configuration from JSON file with env var overrides."""
        config_data = {}
        
        if config_path.exists():
            with open(config_path) as f:
                config_data = json.load(f)
        
        return cls(**config_data)
    
    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get default config file path."""
        return Path.home() / ".llm-service" / "monitoring_config.json"
    
    def save_to_file(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to JSON file."""
        path = config_path or self.get_default_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)
    
    def get_enabled_checks(self) -> List[ServiceCheck]:
        """Get list of enabled service checks."""
        return [c for c in self.checks if c.enabled]
    
    def get_threshold(self, metric_name: str, check: Optional[ServiceCheck] = None) -> Optional[ThresholdRule]:
        """Get threshold rule for a metric, check-specific overrides global."""
        # Check-specific thresholds first
        if check:
            for rule in check.thresholds:
                if rule.metric_name == metric_name and rule.enabled:
                    return rule
        
        # Fall back to global defaults
        return self.default_thresholds.get(metric_name)
    
    def add_check(self, check: ServiceCheck) -> None:
        """Add a service check."""
        # Replace if exists
        self.checks = [c for c in self.checks if c.name != check.name]
        self.checks.append(check)
    
    def remove_check(self, name: str) -> bool:
        """Remove a service check by name."""
        original_len = len(self.checks)
        self.checks = [c for c in self.checks if c.name != name]
        return len(self.checks) < original_len


# Sample configuration template
SAMPLE_CONFIG = {
    "poll_interval_seconds": 60,
    "parallel_checks": True,
    "checks": [
        {
            "name": "payment-api-errors",
            "service": "splunk",
            "tool": "get_splunk_error_rate",
            "arguments": {
                "index": "main",
                "service_name": "payment-api",
                "time_range": "-15m",
            },
            "interval_seconds": 60,
            "thresholds": [
                {"metric_name": "error_rate", "warning": 1.0, "critical": 5.0, "comparison": "gt"}
            ],
        },
        {
            "name": "order-consumer-lag",
            "service": "kafka",
            "tool": "check_kafka_lag",
            "arguments": {
                "consumer_group": "order-processor",
                "topics": ["orders", "order-events"],
            },
            "interval_seconds": 30,
            "thresholds": [
                {"metric_name": "kafka_lag", "warning": 100, "critical": 1000, "comparison": "gt"}
            ],
        },
        {
            "name": "app-jvm-health",
            "service": "appdynamics",
            "tool": "get_jvm_metrics",
            "arguments": {
                "application_name": "MyApp",
                "tier_name": "WebTier",
                "duration_minutes": 15,
            },
            "interval_seconds": 60,
            "thresholds": [
                {"metric_name": "jvm_heap", "warning": 80.0, "critical": 95.0, "comparison": "gt"}
            ],
        },
        {
            "name": "mongodb-health",
            "service": "mongodb",
            "tool": "get_mongodb_status",
            "arguments": {},
            "interval_seconds": 60,
            "thresholds": [
                {"metric_name": "mongodb_connections", "warning": 1000, "critical": 5000, "comparison": "gt"}
            ],
        },
    ],
    "teams": {
        "webhook_url": "",
        "enabled": True,
        "min_severity": "warning",
        "rate_limit_seconds": 300,
    },
    "database": {
        "sqlite_path": "~/.llm-service/monitoring.db",
        "retention_days": 30,
    },
    "mcp": {
        "command": "monitoring-mcp",
        "timeout_seconds": 30,
    },
}


def create_sample_config(path: Optional[Path] = None) -> Path:
    """Create a sample configuration file."""
    config_path = path or MonitoringAgentConfig.get_default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, "w") as f:
        json.dump(SAMPLE_CONFIG, f, indent=2)
    
    return config_path
