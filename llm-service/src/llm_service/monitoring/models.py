"""
Data models for the Monitoring Agent.

SQLite-compatible Pydantic models for metrics, alerts, and health checks.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HealthStatus(str, Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    ERROR = "error"


class MetricRecord(BaseModel):
    """
    A single metric measurement record.
    
    Stored in SQLite `metrics` table.
    """
    id: Optional[int] = Field(default=None, description="Auto-increment ID")
    
    # Identification
    check_name: str = Field(..., description="Service check name")
    service: str = Field(..., description="Service type (splunk, kafka, etc.)")
    metric_name: str = Field(..., description="Metric name (e.g., 'error_rate', 'lag')")
    
    # Values
    value: float = Field(..., description="Metric value")
    unit: Optional[str] = Field(default=None, description="Unit (%, ms, count, etc.)")
    
    # Status
    status: HealthStatus = Field(default=HealthStatus.UNKNOWN, description="Health status")
    threshold_warning: Optional[float] = Field(default=None, description="Warning threshold")
    threshold_critical: Optional[float] = Field(default=None, description="Critical threshold")
    
    # Context
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    
    # Timestamps
    collected_at: datetime = Field(default_factory=datetime.now, description="Collection time")
    
    def to_sqlite_row(self) -> tuple:
        """Convert to SQLite row tuple."""
        import json
        return (
            self.check_name,
            self.service,
            self.metric_name,
            self.value,
            self.unit,
            self.status.value,
            self.threshold_warning,
            self.threshold_critical,
            json.dumps(self.metadata),
            self.collected_at.isoformat(),
        )
    
    @classmethod
    def from_sqlite_row(cls, row: tuple) -> "MetricRecord":
        """Create from SQLite row."""
        import json
        return cls(
            id=row[0],
            check_name=row[1],
            service=row[2],
            metric_name=row[3],
            value=row[4],
            unit=row[5],
            status=HealthStatus(row[6]),
            threshold_warning=row[7],
            threshold_critical=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
            collected_at=datetime.fromisoformat(row[10]),
        )


class Alert(BaseModel):
    """
    An alert generated from threshold violation.
    
    Stored in SQLite `alerts` table.
    """
    id: Optional[int] = Field(default=None, description="Auto-increment ID")
    
    # Identification
    check_name: str = Field(..., description="Source service check")
    service: str = Field(..., description="Service type")
    metric_name: str = Field(..., description="Metric that triggered alert")
    
    # Alert details
    severity: AlertSeverity = Field(..., description="Alert severity")
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message")
    
    # Values
    current_value: float = Field(..., description="Current metric value")
    threshold_value: float = Field(..., description="Threshold that was exceeded")
    
    # State tracking
    is_active: bool = Field(default=True, description="Whether alert is still active")
    acknowledged: bool = Field(default=False, description="Whether alert was acknowledged")
    acknowledged_by: Optional[str] = Field(default=None, description="Who acknowledged")
    acknowledged_at: Optional[datetime] = Field(default=None, description="When acknowledged")
    
    # Notification tracking
    notified: bool = Field(default=False, description="Whether notification was sent")
    notified_at: Optional[datetime] = Field(default=None, description="When notified")
    notification_channel: Optional[str] = Field(default=None, description="Notification channel (teams, etc.)")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now, description="Alert creation time")
    resolved_at: Optional[datetime] = Field(default=None, description="When alert was resolved")
    
    # Context
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    
    def to_sqlite_row(self) -> tuple:
        """Convert to SQLite row tuple."""
        import json
        return (
            self.check_name,
            self.service,
            self.metric_name,
            self.severity.value,
            self.title,
            self.message,
            self.current_value,
            self.threshold_value,
            self.is_active,
            self.acknowledged,
            self.acknowledged_by,
            self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            self.notified,
            self.notified_at.isoformat() if self.notified_at else None,
            self.notification_channel,
            self.created_at.isoformat(),
            self.resolved_at.isoformat() if self.resolved_at else None,
            json.dumps(self.metadata),
        )
    
    @classmethod
    def from_sqlite_row(cls, row: tuple) -> "Alert":
        """Create from SQLite row."""
        import json
        return cls(
            id=row[0],
            check_name=row[1],
            service=row[2],
            metric_name=row[3],
            severity=AlertSeverity(row[4]),
            title=row[5],
            message=row[6],
            current_value=row[7],
            threshold_value=row[8],
            is_active=bool(row[9]),
            acknowledged=bool(row[10]),
            acknowledged_by=row[11],
            acknowledged_at=datetime.fromisoformat(row[12]) if row[12] else None,
            notified=bool(row[13]),
            notified_at=datetime.fromisoformat(row[14]) if row[14] else None,
            notification_channel=row[15],
            created_at=datetime.fromisoformat(row[16]),
            resolved_at=datetime.fromisoformat(row[17]) if row[17] else None,
            metadata=json.loads(row[18]) if row[18] else {},
        )


class HealthCheck(BaseModel):
    """
    Result of a health check execution.
    
    Stored in SQLite `health_checks` table.
    """
    id: Optional[int] = Field(default=None, description="Auto-increment ID")
    
    # Identification
    check_name: str = Field(..., description="Service check name")
    service: str = Field(..., description="Service type")
    
    # Result
    status: HealthStatus = Field(..., description="Overall health status")
    message: Optional[str] = Field(default=None, description="Status message")
    
    # Metrics collected
    metrics: List[MetricRecord] = Field(default_factory=list, description="Collected metrics")
    
    # Alerts generated
    alerts: List[Alert] = Field(default_factory=list, description="Alerts generated")
    
    # Execution details
    started_at: datetime = Field(default_factory=datetime.now, description="Check start time")
    completed_at: Optional[datetime] = Field(default=None, description="Check completion time")
    duration_seconds: float = Field(default=0, description="Execution duration")
    
    # Error handling
    error: Optional[str] = Field(default=None, description="Error message if check failed")
    
    # Raw response
    raw_response: Optional[str] = Field(default=None, description="Raw MCP response")
    
    def to_sqlite_row(self) -> tuple:
        """Convert to SQLite row tuple (without nested objects)."""
        return (
            self.check_name,
            self.service,
            self.status.value,
            self.message,
            self.started_at.isoformat(),
            self.completed_at.isoformat() if self.completed_at else None,
            self.duration_seconds,
            self.error,
            self.raw_response,
        )
    
    @classmethod
    def from_sqlite_row(cls, row: tuple) -> "HealthCheck":
        """Create from SQLite row."""
        return cls(
            id=row[0],
            check_name=row[1],
            service=row[2],
            status=HealthStatus(row[3]),
            message=row[4],
            started_at=datetime.fromisoformat(row[5]),
            completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
            duration_seconds=row[7],
            error=row[8],
            raw_response=row[9],
        )


class CheckResult(BaseModel):
    """
    Complete result from running a service check.
    
    Used internally, not stored directly.
    """
    check_name: str
    service: str
    status: HealthStatus
    
    # Collected data
    health_check: HealthCheck
    metrics: List[MetricRecord]
    alerts: List[Alert]
    
    # Timing
    duration_seconds: float
    
    # Raw response from MCP
    raw_response: Optional[str] = None


class MonitoringSummary(BaseModel):
    """Summary of monitoring status across all checks."""
    
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Overall status
    overall_status: HealthStatus = Field(default=HealthStatus.UNKNOWN)
    
    # Counts
    total_checks: int = Field(default=0)
    healthy_checks: int = Field(default=0)
    warning_checks: int = Field(default=0)
    critical_checks: int = Field(default=0)
    error_checks: int = Field(default=0)
    
    # Active alerts
    active_alerts: int = Field(default=0)
    unacknowledged_alerts: int = Field(default=0)
    
    # Per-service status
    service_status: Dict[str, HealthStatus] = Field(default_factory=dict)
    
    # Recent checks
    recent_checks: List[HealthCheck] = Field(default_factory=list)
    
    def update_from_results(self, results: List[CheckResult]) -> None:
        """Update summary from check results."""
        self.total_checks = len(results)
        self.healthy_checks = 0
        self.warning_checks = 0
        self.critical_checks = 0
        self.error_checks = 0
        
        service_statuses: Dict[str, List[HealthStatus]] = {}
        
        for result in results:
            # Count by status
            if result.status == HealthStatus.HEALTHY:
                self.healthy_checks += 1
            elif result.status == HealthStatus.WARNING:
                self.warning_checks += 1
            elif result.status == HealthStatus.CRITICAL:
                self.critical_checks += 1
            elif result.status == HealthStatus.ERROR:
                self.error_checks += 1
            
            # Group by service
            if result.service not in service_statuses:
                service_statuses[result.service] = []
            service_statuses[result.service].append(result.status)
            
            # Count alerts
            for alert in result.alerts:
                if alert.is_active:
                    self.active_alerts += 1
                    if not alert.acknowledged:
                        self.unacknowledged_alerts += 1
            
            # Track recent
            self.recent_checks.append(result.health_check)
        
        # Determine per-service status (worst wins)
        for service, statuses in service_statuses.items():
            if HealthStatus.CRITICAL in statuses or HealthStatus.ERROR in statuses:
                self.service_status[service] = HealthStatus.CRITICAL
            elif HealthStatus.WARNING in statuses:
                self.service_status[service] = HealthStatus.WARNING
            else:
                self.service_status[service] = HealthStatus.HEALTHY
        
        # Determine overall status
        if self.critical_checks > 0 or self.error_checks > 0:
            self.overall_status = HealthStatus.CRITICAL
        elif self.warning_checks > 0:
            self.overall_status = HealthStatus.WARNING
        elif self.healthy_checks > 0:
            self.overall_status = HealthStatus.HEALTHY
