"""
Monitoring MCP Server

MCP server providing tools for infrastructure monitoring:
- Splunk log search and analysis
- AppDynamics application performance metrics
- Kafka consumer lag and broker health
- MongoDB server status and replica health
"""

__version__ = "0.1.0"

from monitoring_mcp.config import MonitoringConfig, ServiceConfig
from monitoring_mcp.auth import AuthProvider, get_auth_provider
from monitoring_mcp.models import (
    HealthStatus,
    MetricResult,
    SplunkSearchResult,
    JvmMetrics,
    KafkaLagResult,
    MongoDBStatus,
)

__all__ = [
    "__version__",
    "MonitoringConfig",
    "ServiceConfig",
    "AuthProvider",
    "get_auth_provider",
    "HealthStatus",
    "MetricResult",
    "SplunkSearchResult",
    "JvmMetrics",
    "KafkaLagResult",
    "MongoDBStatus",
]
