"""
Server Monitoring Agent

Automated infrastructure monitoring that polls metrics from Splunk, AppDynamics,
Kafka, and MongoDB via the monitoring-mcp server. Stores metrics in SQLite
and sends alerts to Microsoft Teams.

Usage:
    # CLI
    python -m llm_service.monitoring start -c config.json
    python -m llm_service.monitoring check -c config.json kafka-consumer-lag
    python -m llm_service.monitoring report -c config.json
    python -m llm_service.monitoring alerts -c config.json --active
    
    # Programmatic
    from llm_service.monitoring import MonitoringOrchestrator, MonitoringAgentConfig
    
    config = MonitoringAgentConfig.from_json("config.json")
    orchestrator = MonitoringOrchestrator(config, storage, notifier)
    await orchestrator.start_polling()
"""

__version__ = "0.1.0"

from .config import (
    MonitoringAgentConfig,
    ServiceCheck,
    ThresholdRule,
    TeamsConfig,
    DatabaseConfig,
    MCPConfig,
    SAMPLE_CONFIG,
)
from .models import (
    MetricRecord,
    Alert,
    AlertSeverity,
    HealthCheck,
    HealthStatus,
    CheckResult,
    MonitoringSummary,
)
from .storage import MetricsStorage
from .notifier import TeamsNotifier
from .orchestrator import MonitoringOrchestrator, MCPClient

__all__ = [
    "__version__",
    # Config
    "MonitoringAgentConfig",
    "ServiceCheck",
    "ThresholdRule",
    "TeamsConfig",
    "DatabaseConfig",
    "MCPConfig",
    "SAMPLE_CONFIG",
    # Models
    "MetricRecord",
    "Alert",
    "AlertSeverity",
    "HealthCheck",
    "HealthStatus",
    "CheckResult",
    "MonitoringSummary",
    # Components
    "MetricsStorage",
    "TeamsNotifier",
    "MonitoringOrchestrator",
    "MCPClient",
]
