"""
SQLite storage for monitoring metrics, alerts, and health checks.

Provides persistent storage with automatic retention management.
"""

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from .config import DatabaseConfig
from .models import (
    Alert,
    AlertSeverity,
    HealthCheck,
    HealthStatus,
    MetricRecord,
    MonitoringSummary,
)


class MetricsStorage:
    """
    SQLite-based storage for monitoring data.
    
    Features:
    - Stores metrics, alerts, and health checks
    - Automatic retention management
    - Query helpers for reports and dashboards
    """
    
    # SQL Schema
    SCHEMA = """
    -- Metrics table
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_name TEXT NOT NULL,
        service TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT,
        status TEXT NOT NULL,
        threshold_warning REAL,
        threshold_critical REAL,
        metadata TEXT,
        collected_at TEXT NOT NULL,
        
        -- Indexes for common queries
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_metrics_check_name ON metrics(check_name);
    CREATE INDEX IF NOT EXISTS idx_metrics_service ON metrics(service);
    CREATE INDEX IF NOT EXISTS idx_metrics_collected_at ON metrics(collected_at);
    CREATE INDEX IF NOT EXISTS idx_metrics_status ON metrics(status);
    
    -- Alerts table
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_name TEXT NOT NULL,
        service TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        current_value REAL NOT NULL,
        threshold_value REAL NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        acknowledged INTEGER NOT NULL DEFAULT 0,
        acknowledged_by TEXT,
        acknowledged_at TEXT,
        notified INTEGER NOT NULL DEFAULT 0,
        notified_at TEXT,
        notification_channel TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        metadata TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_alerts_check_name ON alerts(check_name);
    CREATE INDEX IF NOT EXISTS idx_alerts_service ON alerts(service);
    CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
    CREATE INDEX IF NOT EXISTS idx_alerts_is_active ON alerts(is_active);
    CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
    
    -- Health checks table
    CREATE TABLE IF NOT EXISTS health_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_name TEXT NOT NULL,
        service TEXT NOT NULL,
        status TEXT NOT NULL,
        message TEXT,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        duration_seconds REAL NOT NULL,
        error TEXT,
        raw_response TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_health_checks_check_name ON health_checks(check_name);
    CREATE INDEX IF NOT EXISTS idx_health_checks_service ON health_checks(service);
    CREATE INDEX IF NOT EXISTS idx_health_checks_started_at ON health_checks(started_at);
    """
    
    def __init__(self, config: DatabaseConfig):
        """Initialize storage with configuration."""
        self.config = config
        self.db_path = Path(config.sqlite_path)
        self._ensure_db_exists()
    
    def _ensure_db_exists(self) -> None:
        """Ensure database file and schema exist."""
        # Create parent directories
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create schema
        with self._get_connection() as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()
    
    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()
    
    # ========== Metrics Operations ==========
    
    def save_metric(self, metric: MetricRecord) -> int:
        """Save a single metric record. Returns the new ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO metrics (
                    check_name, service, metric_name, value, unit,
                    status, threshold_warning, threshold_critical,
                    metadata, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                metric.to_sqlite_row()
            )
            conn.commit()
            return cursor.lastrowid or 0
    
    def save_metrics(self, metrics: List[MetricRecord]) -> List[int]:
        """Save multiple metrics. Returns list of new IDs."""
        ids = []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for metric in metrics:
                cursor.execute(
                    """
                    INSERT INTO metrics (
                        check_name, service, metric_name, value, unit,
                        status, threshold_warning, threshold_critical,
                        metadata, collected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    metric.to_sqlite_row()
                )
                ids.append(cursor.lastrowid or 0)
            conn.commit()
        return ids
    
    def get_metrics(
        self,
        check_name: Optional[str] = None,
        service: Optional[str] = None,
        metric_name: Optional[str] = None,
        status: Optional[HealthStatus] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MetricRecord]:
        """Query metrics with filters."""
        conditions = []
        params: List[Any] = []
        
        if check_name:
            conditions.append("check_name = ?")
            params.append(check_name)
        if service:
            conditions.append("service = ?")
            params.append(service)
        if metric_name:
            conditions.append("metric_name = ?")
            params.append(metric_name)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if since:
            conditions.append("collected_at >= ?")
            params.append(since.isoformat())
        if until:
            conditions.append("collected_at <= ?")
            params.append(until.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, check_name, service, metric_name, value, unit,
                       status, threshold_warning, threshold_critical,
                       metadata, collected_at
                FROM metrics
                WHERE {where_clause}
                ORDER BY collected_at DESC
                LIMIT ?
                """,
                params + [limit]
            )
            return [MetricRecord.from_sqlite_row(row) for row in cursor.fetchall()]
    
    def get_latest_metric(
        self,
        check_name: str,
        metric_name: str,
    ) -> Optional[MetricRecord]:
        """Get the most recent metric for a check."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, check_name, service, metric_name, value, unit,
                       status, threshold_warning, threshold_critical,
                       metadata, collected_at
                FROM metrics
                WHERE check_name = ? AND metric_name = ?
                ORDER BY collected_at DESC
                LIMIT 1
                """,
                (check_name, metric_name)
            )
            row = cursor.fetchone()
            return MetricRecord.from_sqlite_row(row) if row else None
    
    # ========== Alerts Operations ==========
    
    def save_alert(self, alert: Alert) -> int:
        """Save a new alert. Returns the new ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO alerts (
                    check_name, service, metric_name, severity, title, message,
                    current_value, threshold_value, is_active, acknowledged,
                    acknowledged_by, acknowledged_at, notified, notified_at,
                    notification_channel, created_at, resolved_at, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                alert.to_sqlite_row()
            )
            conn.commit()
            return cursor.lastrowid or 0
    
    def update_alert(self, alert: Alert) -> None:
        """Update an existing alert."""
        if alert.id is None:
            raise ValueError("Alert must have an ID to update")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alerts SET
                    is_active = ?,
                    acknowledged = ?,
                    acknowledged_by = ?,
                    acknowledged_at = ?,
                    notified = ?,
                    notified_at = ?,
                    notification_channel = ?,
                    resolved_at = ?,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    alert.is_active,
                    alert.acknowledged,
                    alert.acknowledged_by,
                    alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    alert.notified,
                    alert.notified_at.isoformat() if alert.notified_at else None,
                    alert.notification_channel,
                    alert.resolved_at.isoformat() if alert.resolved_at else None,
                    json.dumps(alert.metadata),
                    alert.id,
                )
            )
            conn.commit()
    
    def get_alerts(
        self,
        check_name: Optional[str] = None,
        service: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
        is_active: Optional[bool] = None,
        acknowledged: Optional[bool] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Alert]:
        """Query alerts with filters."""
        conditions = []
        params: List[Any] = []
        
        if check_name:
            conditions.append("check_name = ?")
            params.append(check_name)
        if service:
            conditions.append("service = ?")
            params.append(service)
        if severity:
            conditions.append("severity = ?")
            params.append(severity.value)
        if is_active is not None:
            conditions.append("is_active = ?")
            params.append(1 if is_active else 0)
        if acknowledged is not None:
            conditions.append("acknowledged = ?")
            params.append(1 if acknowledged else 0)
        if since:
            conditions.append("created_at >= ?")
            params.append(since.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, check_name, service, metric_name, severity, title, message,
                       current_value, threshold_value, is_active, acknowledged,
                       acknowledged_by, acknowledged_at, notified, notified_at,
                       notification_channel, created_at, resolved_at, metadata
                FROM alerts
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [limit]
            )
            return [Alert.from_sqlite_row(row) for row in cursor.fetchall()]
    
    def get_active_alert_for_check(
        self,
        check_name: str,
        metric_name: str,
    ) -> Optional[Alert]:
        """Get active alert for a specific check and metric."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, check_name, service, metric_name, severity, title, message,
                       current_value, threshold_value, is_active, acknowledged,
                       acknowledged_by, acknowledged_at, notified, notified_at,
                       notification_channel, created_at, resolved_at, metadata
                FROM alerts
                WHERE check_name = ? AND metric_name = ? AND is_active = 1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (check_name, metric_name)
            )
            row = cursor.fetchone()
            return Alert.from_sqlite_row(row) if row else None
    
    def acknowledge_alert(
        self,
        alert_id: int,
        acknowledged_by: str = "system",
    ) -> None:
        """Mark an alert as acknowledged."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alerts SET
                    acknowledged = 1,
                    acknowledged_by = ?,
                    acknowledged_at = ?
                WHERE id = ?
                """,
                (acknowledged_by, datetime.now().isoformat(), alert_id)
            )
            conn.commit()
    
    def resolve_alert(self, alert_id: int) -> None:
        """Mark an alert as resolved."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alerts SET
                    is_active = 0,
                    resolved_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), alert_id)
            )
            conn.commit()
    
    def mark_alert_notified(
        self,
        alert_id: int,
        channel: str = "teams",
    ) -> None:
        """Mark an alert as having been notified."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE alerts SET
                    notified = 1,
                    notified_at = ?,
                    notification_channel = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), channel, alert_id)
            )
            conn.commit()
    
    # ========== Health Checks Operations ==========
    
    def save_health_check(self, check: HealthCheck) -> int:
        """Save a health check record. Returns the new ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO health_checks (
                    check_name, service, status, message,
                    started_at, completed_at, duration_seconds,
                    error, raw_response
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                check.to_sqlite_row()
            )
            conn.commit()
            return cursor.lastrowid or 0
    
    def get_health_checks(
        self,
        check_name: Optional[str] = None,
        service: Optional[str] = None,
        status: Optional[HealthStatus] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[HealthCheck]:
        """Query health checks with filters."""
        conditions = []
        params: List[Any] = []
        
        if check_name:
            conditions.append("check_name = ?")
            params.append(check_name)
        if service:
            conditions.append("service = ?")
            params.append(service)
        if status:
            conditions.append("status = ?")
            params.append(status.value)
        if since:
            conditions.append("started_at >= ?")
            params.append(since.isoformat())
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, check_name, service, status, message,
                       started_at, completed_at, duration_seconds,
                       error, raw_response
                FROM health_checks
                WHERE {where_clause}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                params + [limit]
            )
            return [HealthCheck.from_sqlite_row(row) for row in cursor.fetchall()]
    
    def get_latest_health_check(self, check_name: str) -> Optional[HealthCheck]:
        """Get the most recent health check for a check name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, check_name, service, status, message,
                       started_at, completed_at, duration_seconds,
                       error, raw_response
                FROM health_checks
                WHERE check_name = ?
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (check_name,)
            )
            row = cursor.fetchone()
            return HealthCheck.from_sqlite_row(row) if row else None
    
    # ========== Summary and Statistics ==========
    
    def get_summary(self, hours: int = 24) -> MonitoringSummary:
        """Get monitoring summary for the specified period."""
        since = datetime.now() - timedelta(hours=hours)
        summary = MonitoringSummary()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get status counts
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM (
                    SELECT check_name, status,
                           ROW_NUMBER() OVER (PARTITION BY check_name ORDER BY started_at DESC) as rn
                    FROM health_checks
                    WHERE started_at >= ?
                )
                WHERE rn = 1
                GROUP BY status
                """,
                (since.isoformat(),)
            )
            
            for row in cursor.fetchall():
                status_str, count = row
                if status_str == HealthStatus.HEALTHY.value:
                    summary.healthy_checks = count
                elif status_str == HealthStatus.WARNING.value:
                    summary.warning_checks = count
                elif status_str == HealthStatus.CRITICAL.value:
                    summary.critical_checks = count
                elif status_str == HealthStatus.ERROR.value:
                    summary.error_checks = count
            
            summary.total_checks = (
                summary.healthy_checks + summary.warning_checks +
                summary.critical_checks + summary.error_checks
            )
            
            # Get active alerts count
            cursor.execute(
                "SELECT COUNT(*) FROM alerts WHERE is_active = 1"
            )
            summary.active_alerts = cursor.fetchone()[0]
            
            # Get unacknowledged alerts
            cursor.execute(
                "SELECT COUNT(*) FROM alerts WHERE is_active = 1 AND acknowledged = 0"
            )
            summary.unacknowledged_alerts = cursor.fetchone()[0]
            
            # Get per-service status
            cursor.execute(
                """
                SELECT service, status
                FROM (
                    SELECT service, status,
                           ROW_NUMBER() OVER (PARTITION BY service ORDER BY started_at DESC) as rn
                    FROM health_checks
                    WHERE started_at >= ?
                )
                WHERE rn = 1
                """,
                (since.isoformat(),)
            )
            
            for row in cursor.fetchall():
                service, status_str = row
                summary.service_status[service] = HealthStatus(status_str)
            
            # Determine overall status
            if summary.critical_checks > 0 or summary.error_checks > 0:
                summary.overall_status = HealthStatus.CRITICAL
            elif summary.warning_checks > 0:
                summary.overall_status = HealthStatus.WARNING
            elif summary.healthy_checks > 0:
                summary.overall_status = HealthStatus.HEALTHY
        
        return summary
    
    def get_metric_history(
        self,
        check_name: str,
        metric_name: str,
        hours: int = 24,
    ) -> List[MetricRecord]:
        """Get metric history for graphing."""
        since = datetime.now() - timedelta(hours=hours)
        return self.get_metrics(
            check_name=check_name,
            metric_name=metric_name,
            since=since,
            limit=1000,  # More data points for graphs
        )
    
    # ========== Retention Management ==========
    
    def cleanup_old_data(self) -> Dict[str, int]:
        """Delete data older than retention period. Returns counts of deleted records."""
        cutoff = datetime.now() - timedelta(days=self.config.retention_days)
        cutoff_str = cutoff.isoformat()
        
        deleted = {"metrics": 0, "health_checks": 0, "alerts": 0}
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete old metrics
            cursor.execute(
                "DELETE FROM metrics WHERE collected_at < ?",
                (cutoff_str,)
            )
            deleted["metrics"] = cursor.rowcount
            
            # Delete old health checks
            cursor.execute(
                "DELETE FROM health_checks WHERE started_at < ?",
                (cutoff_str,)
            )
            deleted["health_checks"] = cursor.rowcount
            
            # Delete old resolved alerts
            cursor.execute(
                """
                DELETE FROM alerts 
                WHERE is_active = 0 AND created_at < ?
                """,
                (cutoff_str,)
            )
            deleted["alerts"] = cursor.rowcount
            
            conn.commit()
        
        return deleted
    
    def vacuum(self) -> None:
        """Optimize database by running VACUUM."""
        with self._get_connection() as conn:
            conn.execute("VACUUM")
