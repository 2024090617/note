"""
Data models for monitoring metrics and results.

Pydantic models for structured responses from all monitoring tools.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class MetricResult(BaseModel):
    """Base model for metric results."""
    
    service: str = Field(..., description="Service name (splunk, appdynamics, kafka, mongodb)")
    status: HealthStatus = Field(default=HealthStatus.UNKNOWN, description="Health status")
    timestamp: datetime = Field(default_factory=datetime.now, description="Collection timestamp")
    alerts: List[str] = Field(default_factory=list, description="Alert messages")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


# =============================================================================
# Splunk Models
# =============================================================================

class SplunkLogEntry(BaseModel):
    """Single Splunk log entry."""
    
    time: str = Field(..., description="Event timestamp")
    source: str = Field(default="", description="Log source")
    sourcetype: str = Field(default="", description="Source type")
    host: str = Field(default="", description="Host name")
    raw: str = Field(default="", description="Raw log message")
    fields: Dict[str, Any] = Field(default_factory=dict, description="Extracted fields")


class SplunkSearchResult(MetricResult):
    """Splunk search results."""
    
    service: str = "splunk"
    query: str = Field(..., description="SPL query executed")
    result_count: int = Field(default=0, description="Total results found")
    events: List[SplunkLogEntry] = Field(default_factory=list, description="Log events")
    
    # Error rate specific
    total_requests: Optional[int] = Field(default=None, description="Total requests in time range")
    error_count: Optional[int] = Field(default=None, description="Error count")
    error_rate: Optional[float] = Field(default=None, description="Error rate percentage")
    error_breakdown: Optional[Dict[str, int]] = Field(default=None, description="Errors by status code")


# =============================================================================
# AppDynamics Models
# =============================================================================

class JvmMetrics(BaseModel):
    """JVM metrics from AppDynamics."""
    
    heap_used_mb: float = Field(default=0, description="Heap memory used (MB)")
    heap_max_mb: float = Field(default=0, description="Max heap memory (MB)")
    heap_usage_percent: float = Field(default=0, description="Heap usage percentage")
    
    gc_time_ms: float = Field(default=0, description="GC time in period (ms)")
    gc_count: int = Field(default=0, description="GC count in period")
    
    thread_count: int = Field(default=0, description="Current thread count")
    thread_blocked: int = Field(default=0, description="Blocked threads")
    
    cpu_usage_percent: float = Field(default=0, description="CPU usage percentage")


class BusinessTransactionMetrics(BaseModel):
    """Business transaction metrics."""
    
    name: str = Field(..., description="Transaction name")
    calls_per_minute: float = Field(default=0, description="Calls per minute")
    avg_response_time_ms: float = Field(default=0, description="Average response time (ms)")
    error_rate: float = Field(default=0, description="Error rate percentage")
    errors_per_minute: float = Field(default=0, description="Errors per minute")
    slow_calls: int = Field(default=0, description="Slow call count")
    very_slow_calls: int = Field(default=0, description="Very slow call count")
    stall_count: int = Field(default=0, description="Stalled call count")


class AppDynamicsResult(MetricResult):
    """AppDynamics metrics result."""
    
    service: str = "appdynamics"
    application_name: str = Field(..., description="Application name")
    tier_name: Optional[str] = Field(default=None, description="Tier name")
    duration_minutes: int = Field(default=15, description="Metrics duration")
    
    jvm: Optional[JvmMetrics] = Field(default=None, description="JVM metrics")
    transactions: List[BusinessTransactionMetrics] = Field(
        default_factory=list, description="Business transaction metrics"
    )
    
    # Overall health
    overall_error_rate: Optional[float] = Field(default=None, description="Overall error rate")
    overall_response_time: Optional[float] = Field(default=None, description="Overall avg response time")


# =============================================================================
# Kafka Models
# =============================================================================

class PartitionLag(BaseModel):
    """Lag for a single partition."""
    
    partition: int = Field(..., description="Partition number")
    current_offset: int = Field(default=0, description="Current consumer offset")
    end_offset: int = Field(default=0, description="End offset (latest)")
    lag: int = Field(default=0, description="Lag (end - current)")


class TopicLag(BaseModel):
    """Lag for a topic across all partitions."""
    
    topic: str = Field(..., description="Topic name")
    partitions: List[PartitionLag] = Field(default_factory=list, description="Per-partition lag")
    total_lag: int = Field(default=0, description="Total lag across partitions")
    max_partition_lag: int = Field(default=0, description="Maximum lag in any partition")


class KafkaLagResult(MetricResult):
    """Kafka consumer lag result."""
    
    service: str = "kafka"
    consumer_group: str = Field(..., description="Consumer group name")
    topics: List[TopicLag] = Field(default_factory=list, description="Per-topic lag")
    total_lag: int = Field(default=0, description="Total lag across all topics")
    
    # Thresholds
    lag_threshold_warning: int = Field(default=100, description="Warning threshold")
    lag_threshold_critical: int = Field(default=1000, description="Critical threshold")


class KafkaBrokerInfo(BaseModel):
    """Kafka broker information."""
    
    broker_id: int = Field(..., description="Broker ID")
    host: str = Field(default="", description="Broker host")
    port: int = Field(default=9092, description="Broker port")
    rack: Optional[str] = Field(default=None, description="Rack ID")
    is_controller: bool = Field(default=False, description="Is cluster controller")


class KafkaClusterHealth(MetricResult):
    """Kafka cluster health result."""
    
    service: str = "kafka"
    brokers: List[KafkaBrokerInfo] = Field(default_factory=list, description="Broker list")
    broker_count: int = Field(default=0, description="Total brokers")
    controller_id: Optional[int] = Field(default=None, description="Controller broker ID")
    topic_count: int = Field(default=0, description="Total topics")
    partition_count: int = Field(default=0, description="Total partitions")


# =============================================================================
# MongoDB Models
# =============================================================================

class MongoDBConnectionStats(BaseModel):
    """MongoDB connection statistics."""
    
    current: int = Field(default=0, description="Current connections")
    available: int = Field(default=0, description="Available connections")
    total_created: int = Field(default=0, description="Total connections created")
    active: int = Field(default=0, description="Active connections")


class MongoDBOperationStats(BaseModel):
    """MongoDB operation statistics."""
    
    insert: int = Field(default=0, description="Insert operations")
    query: int = Field(default=0, description="Query operations")
    update: int = Field(default=0, description="Update operations")
    delete: int = Field(default=0, description="Delete operations")
    getmore: int = Field(default=0, description="GetMore operations")
    command: int = Field(default=0, description="Command operations")


class MongoDBReplicaMember(BaseModel):
    """MongoDB replica set member."""
    
    name: str = Field(..., description="Member name (host:port)")
    state: str = Field(default="", description="State (PRIMARY, SECONDARY, etc.)")
    state_str: str = Field(default="", description="State string")
    health: int = Field(default=1, description="Health (1=healthy, 0=unhealthy)")
    uptime: int = Field(default=0, description="Uptime in seconds")
    lag_seconds: Optional[int] = Field(default=None, description="Replication lag (secondaries)")
    is_primary: bool = Field(default=False, description="Is primary")
    is_secondary: bool = Field(default=False, description="Is secondary")


class MongoDBStatus(MetricResult):
    """MongoDB server status result."""
    
    service: str = "mongodb"
    host: str = Field(default="", description="Server host")
    version: str = Field(default="", description="MongoDB version")
    uptime_seconds: int = Field(default=0, description="Server uptime")
    
    connections: MongoDBConnectionStats = Field(
        default_factory=MongoDBConnectionStats, description="Connection stats"
    )
    operations: MongoDBOperationStats = Field(
        default_factory=MongoDBOperationStats, description="Operation stats"
    )
    
    # Memory
    resident_mb: float = Field(default=0, description="Resident memory (MB)")
    virtual_mb: float = Field(default=0, description="Virtual memory (MB)")
    
    # Replica set
    replica_set_name: Optional[str] = Field(default=None, description="Replica set name")
    is_replica_set: bool = Field(default=False, description="Is part of replica set")
    members: List[MongoDBReplicaMember] = Field(
        default_factory=list, description="Replica set members"
    )
    
    # Thresholds
    connections_threshold_warning: int = Field(default=1000, description="Connection warning threshold")
    connections_threshold_critical: int = Field(default=5000, description="Connection critical threshold")


# =============================================================================
# Aggregated Health Check
# =============================================================================

class ServiceHealth(BaseModel):
    """Health status for a single service."""
    
    service: str = Field(..., description="Service name")
    status: HealthStatus = Field(..., description="Health status")
    message: str = Field(default="", description="Status message")
    last_check: datetime = Field(default_factory=datetime.now, description="Last check time")
    metrics: Optional[MetricResult] = Field(default=None, description="Detailed metrics")
    error: Optional[str] = Field(default=None, description="Error message if check failed")


class HealthCheckResult(BaseModel):
    """Complete health check result across all services."""
    
    timestamp: datetime = Field(default_factory=datetime.now, description="Check timestamp")
    overall_status: HealthStatus = Field(default=HealthStatus.UNKNOWN, description="Overall status")
    services: Dict[str, ServiceHealth] = Field(default_factory=dict, description="Per-service health")
    alerts: List[str] = Field(default_factory=list, description="All alerts")
    check_duration_seconds: float = Field(default=0, description="Total check duration")
    
    def add_service_health(self, health: ServiceHealth) -> None:
        """Add service health and update overall status."""
        self.services[health.service] = health
        
        if health.error:
            self.alerts.append(f"[{health.service}] Check failed: {health.error}")
        
        if health.metrics and health.metrics.alerts:
            for alert in health.metrics.alerts:
                self.alerts.append(f"[{health.service}] {alert}")
        
        # Update overall status (worst wins)
        if health.status == HealthStatus.CRITICAL:
            self.overall_status = HealthStatus.CRITICAL
        elif health.status == HealthStatus.WARNING and self.overall_status != HealthStatus.CRITICAL:
            self.overall_status = HealthStatus.WARNING
        elif health.status == HealthStatus.HEALTHY and self.overall_status == HealthStatus.UNKNOWN:
            self.overall_status = HealthStatus.HEALTHY
