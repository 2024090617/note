"""
Monitoring orchestrator for polling and alerting.

Coordinates service checks, threshold evaluation, and alert generation.
"""

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    MonitoringAgentConfig,
    ServiceCheck,
    ThresholdRule,
)
from .models import (
    Alert,
    AlertSeverity,
    CheckResult,
    HealthCheck,
    HealthStatus,
    MetricRecord,
    MonitoringSummary,
)
from .storage import MetricsStorage
from .notifier import TeamsNotifier


class MCPClient:
    """
    Client for communicating with MCP server.
    
    Uses subprocess to call the MCP server tools.
    """
    
    def __init__(self, command: str, timeout_seconds: int = 30):
        """Initialize with MCP server command."""
        self.command = command
        self.timeout = timeout_seconds
        self._process: Optional[subprocess.Popen] = None
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call an MCP tool and return the result.
        
        This uses JSON-RPC format to communicate with the MCP server.
        """
        # Build the JSON-RPC request
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        
        # Run in subprocess
        try:
            # Parse command into parts
            cmd_parts = self.command.split()
            
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            # Send request
            request_bytes = json.dumps(request).encode() + b"\n"
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(request_bytes),
                timeout=self.timeout,
            )
            
            # Parse response
            if stdout:
                response = json.loads(stdout.decode())
                if "result" in response:
                    return response["result"]
                elif "error" in response:
                    raise RuntimeError(f"MCP error: {response['error']}")
            
            if stderr:
                raise RuntimeError(f"MCP stderr: {stderr.decode()}")
            
            return {"error": "No response from MCP server"}
            
        except asyncio.TimeoutError:
            raise RuntimeError(f"MCP call timed out after {self.timeout}s")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid MCP response: {e}")
        except Exception as e:
            raise RuntimeError(f"MCP call failed: {e}")


class MonitoringOrchestrator:
    """
    Orchestrates monitoring checks and alerting.
    
    Features:
    - Polling loop with configurable intervals
    - Per-check scheduling
    - Threshold evaluation and alert generation
    - Recovery detection
    - Notification dispatch
    """
    
    def __init__(
        self,
        config: MonitoringAgentConfig,
        storage: MetricsStorage,
        notifier: Optional[TeamsNotifier] = None,
    ):
        """Initialize orchestrator with configuration."""
        self.config = config
        self.storage = storage
        self.notifier = notifier
        self.mcp_client = MCPClient(
            config.mcp.command,
            config.mcp.timeout_seconds,
        )
        
        # Track last run times for scheduling
        self._last_run: Dict[str, datetime] = {}
        
        # Running state
        self._running = False
        self._tasks: List[asyncio.Task] = []
    
    async def run_check(self, check: ServiceCheck) -> CheckResult:
        """
        Run a single service check.
        
        Returns CheckResult with metrics, status, and any alerts.
        """
        started_at = datetime.now()
        metrics: List[MetricRecord] = []
        alerts: List[Alert] = []
        status = HealthStatus.UNKNOWN
        error: Optional[str] = None
        raw_response: Optional[str] = None
        
        try:
            # Call MCP tool
            result = await self.mcp_client.call_tool(
                check.tool,
                check.arguments,
            )
            raw_response = json.dumps(result)
            
            # Extract metrics from result
            metrics, status = self._extract_metrics(check, result)
            
            # Evaluate thresholds and generate alerts
            alerts = self._evaluate_thresholds(check, metrics)
            
            # Update status based on alerts
            if any(a.severity == AlertSeverity.CRITICAL for a in alerts):
                status = HealthStatus.CRITICAL
            elif any(a.severity == AlertSeverity.WARNING for a in alerts):
                status = HealthStatus.WARNING
            
        except Exception as e:
            error = str(e)
            status = HealthStatus.ERROR
        
        completed_at = datetime.now()
        duration = (completed_at - started_at).total_seconds()
        
        # Create health check record
        health_check = HealthCheck(
            check_name=check.name,
            service=check.service,
            status=status,
            message=error if error else f"Collected {len(metrics)} metrics",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            error=error,
            raw_response=raw_response,
        )
        
        return CheckResult(
            check_name=check.name,
            service=check.service,
            status=status,
            health_check=health_check,
            metrics=metrics,
            alerts=alerts,
            duration_seconds=duration,
            raw_response=raw_response,
        )
    
    def _extract_metrics(
        self,
        check: ServiceCheck,
        result: Dict[str, Any],
    ) -> Tuple[List[MetricRecord], HealthStatus]:
        """Extract metrics from MCP tool result."""
        metrics: List[MetricRecord] = []
        status = HealthStatus.HEALTHY
        
        # Handle different result formats based on tool type
        if check.tool == "check_kafka_lag":
            # Kafka lag result
            if "total_lag" in result:
                metrics.append(MetricRecord(
                    check_name=check.name,
                    service=check.service,
                    metric_name="total_lag",
                    value=float(result["total_lag"]),
                    unit="messages",
                ))
            
            if "topics" in result:
                for topic in result["topics"]:
                    topic_name = topic.get("topic", "unknown")
                    topic_lag = topic.get("total_lag", 0)
                    metrics.append(MetricRecord(
                        check_name=check.name,
                        service=check.service,
                        metric_name=f"topic_lag_{topic_name}",
                        value=float(topic_lag),
                        unit="messages",
                        metadata={"topic": topic_name},
                    ))
            
            if result.get("status") == "critical":
                status = HealthStatus.CRITICAL
            elif result.get("status") == "warning":
                status = HealthStatus.WARNING
        
        elif check.tool == "get_splunk_error_rate":
            # Splunk error rate result
            if "error_rate" in result:
                metrics.append(MetricRecord(
                    check_name=check.name,
                    service=check.service,
                    metric_name="error_rate",
                    value=float(result["error_rate"]),
                    unit="%",
                ))
            
            if "error_count" in result:
                metrics.append(MetricRecord(
                    check_name=check.name,
                    service=check.service,
                    metric_name="error_count",
                    value=float(result["error_count"]),
                    unit="count",
                ))
            
            if result.get("status") == "critical":
                status = HealthStatus.CRITICAL
            elif result.get("status") == "warning":
                status = HealthStatus.WARNING
        
        elif check.tool == "get_jvm_metrics":
            # AppDynamics JVM metrics
            if "heap_used_percentage" in result:
                metrics.append(MetricRecord(
                    check_name=check.name,
                    service=check.service,
                    metric_name="heap_used_percentage",
                    value=float(result["heap_used_percentage"]),
                    unit="%",
                ))
            
            if "gc_time_percentage" in result:
                metrics.append(MetricRecord(
                    check_name=check.name,
                    service=check.service,
                    metric_name="gc_time_percentage",
                    value=float(result["gc_time_percentage"]),
                    unit="%",
                ))
            
            if result.get("status") == "critical":
                status = HealthStatus.CRITICAL
            elif result.get("status") == "warning":
                status = HealthStatus.WARNING
        
        elif check.tool == "get_mongodb_status":
            # MongoDB status
            if "connections" in result:
                conn = result["connections"]
                if "current" in conn:
                    metrics.append(MetricRecord(
                        check_name=check.name,
                        service=check.service,
                        metric_name="connections_current",
                        value=float(conn["current"]),
                        unit="count",
                    ))
            
            if "opcounters" in result:
                for op, count in result["opcounters"].items():
                    metrics.append(MetricRecord(
                        check_name=check.name,
                        service=check.service,
                        metric_name=f"opcounter_{op}",
                        value=float(count),
                        unit="ops",
                    ))
            
            if result.get("status") == "critical":
                status = HealthStatus.CRITICAL
            elif result.get("status") == "warning":
                status = HealthStatus.WARNING
        
        else:
            # Generic handling - try to extract numeric values
            for key, value in result.items():
                if isinstance(value, (int, float)):
                    metrics.append(MetricRecord(
                        check_name=check.name,
                        service=check.service,
                        metric_name=key,
                        value=float(value),
                    ))
        
        return metrics, status
    
    def _evaluate_thresholds(
        self,
        check: ServiceCheck,
        metrics: List[MetricRecord],
    ) -> List[Alert]:
        """Evaluate metrics against thresholds and generate alerts."""
        alerts: List[Alert] = []
        
        for threshold in check.thresholds:
            # Find matching metric
            matching_metrics = [
                m for m in metrics
                if m.metric_name == threshold.metric_name
            ]
            
            if not matching_metrics:
                continue
            
            for metric in matching_metrics:
                # Update metric with threshold values
                metric.threshold_warning = threshold.warning
                metric.threshold_critical = threshold.critical
                
                # Evaluate threshold
                violated, severity = self._check_threshold(
                    metric.value,
                    threshold,
                )
                
                if violated:
                    # Check if there's an existing active alert
                    existing = self.storage.get_active_alert_for_check(
                        check.name,
                        threshold.metric_name,
                    )
                    
                    if existing:
                        # Update existing alert if severity changed
                        if existing.severity != severity:
                            existing.severity = severity
                            existing.current_value = metric.value
                            self.storage.update_alert(existing)
                    else:
                        # Create new alert
                        threshold_value = (
                            threshold.critical
                            if severity == AlertSeverity.CRITICAL
                            else threshold.warning
                        )
                        
                        alert = Alert(
                            check_name=check.name,
                            service=check.service,
                            metric_name=threshold.metric_name,
                            severity=severity,
                            title=f"{check.name} {threshold.metric_name} {severity.value}",
                            message=self._build_alert_message(
                                check, metric, threshold, severity
                            ),
                            current_value=metric.value,
                            threshold_value=threshold_value,
                        )
                        alerts.append(alert)
                    
                    # Update metric status
                    metric.status = (
                        HealthStatus.CRITICAL
                        if severity == AlertSeverity.CRITICAL
                        else HealthStatus.WARNING
                    )
                else:
                    metric.status = HealthStatus.HEALTHY
                    
                    # Check if we should resolve an existing alert
                    existing = self.storage.get_active_alert_for_check(
                        check.name,
                        threshold.metric_name,
                    )
                    if existing:
                        self.storage.resolve_alert(existing.id)
                        # Note: Recovery notification handled separately
        
        return alerts
    
    def _check_threshold(
        self,
        value: float,
        threshold: ThresholdRule,
    ) -> Tuple[bool, AlertSeverity]:
        """Check if value violates threshold. Returns (violated, severity)."""
        comparison = threshold.comparison or ">"
        
        def compare(val: float, thresh: float) -> bool:
            if comparison == ">":
                return val > thresh
            elif comparison == ">=":
                return val >= thresh
            elif comparison == "<":
                return val < thresh
            elif comparison == "<=":
                return val <= thresh
            elif comparison == "==":
                return val == thresh
            return False
        
        # Check critical first
        if threshold.critical is not None and compare(value, threshold.critical):
            return True, AlertSeverity.CRITICAL
        
        # Then warning
        if threshold.warning is not None and compare(value, threshold.warning):
            return True, AlertSeverity.WARNING
        
        return False, AlertSeverity.INFO
    
    def _build_alert_message(
        self,
        check: ServiceCheck,
        metric: MetricRecord,
        threshold: ThresholdRule,
        severity: AlertSeverity,
    ) -> str:
        """Build human-readable alert message."""
        comparison = threshold.comparison or ">"
        threshold_value = (
            threshold.critical
            if severity == AlertSeverity.CRITICAL
            else threshold.warning
        )
        
        return (
            f"The {metric.metric_name} for {check.name} ({check.service}) "
            f"is {metric.value:.2f}{metric.unit or ''}, "
            f"which {comparison} the {severity.value} threshold of "
            f"{threshold_value:.2f}{metric.unit or ''}."
        )
    
    async def run_all_checks(self) -> List[CheckResult]:
        """Run all configured checks."""
        results: List[CheckResult] = []
        
        for check in self.config.checks:
            try:
                result = await self.run_check(check)
                results.append(result)
                
                # Store results
                self.storage.save_health_check(result.health_check)
                if result.metrics:
                    self.storage.save_metrics(result.metrics)
                for alert in result.alerts:
                    alert_id = self.storage.save_alert(alert)
                    alert.id = alert_id
                    
                    # Send notification
                    if self.notifier:
                        success = await self.notifier.send_alert(alert)
                        if success:
                            self.storage.mark_alert_notified(alert_id, "teams")
                
            except Exception as e:
                # Create error result
                health_check = HealthCheck(
                    check_name=check.name,
                    service=check.service,
                    status=HealthStatus.ERROR,
                    message=f"Check failed: {e}",
                    error=str(e),
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                    duration_seconds=0,
                )
                
                results.append(CheckResult(
                    check_name=check.name,
                    service=check.service,
                    status=HealthStatus.ERROR,
                    health_check=health_check,
                    metrics=[],
                    alerts=[],
                    duration_seconds=0,
                ))
                
                self.storage.save_health_check(health_check)
        
        return results
    
    async def run_due_checks(self) -> List[CheckResult]:
        """Run only checks that are due based on their intervals."""
        results: List[CheckResult] = []
        now = datetime.now()
        
        for check in self.config.checks:
            last_run = self._last_run.get(check.name)
            
            if last_run is None:
                # Never run, should run
                should_run = True
            else:
                # Check if interval has elapsed
                elapsed = (now - last_run).total_seconds()
                should_run = elapsed >= check.interval_seconds
            
            if should_run:
                result = await self.run_check(check)
                results.append(result)
                self._last_run[check.name] = now
                
                # Store results
                self.storage.save_health_check(result.health_check)
                if result.metrics:
                    self.storage.save_metrics(result.metrics)
                for alert in result.alerts:
                    alert_id = self.storage.save_alert(alert)
                    alert.id = alert_id
                    
                    if self.notifier:
                        success = await self.notifier.send_alert(alert)
                        if success:
                            self.storage.mark_alert_notified(alert_id, "teams")
        
        return results
    
    async def start_polling(self) -> None:
        """Start the polling loop."""
        self._running = True
        
        while self._running:
            try:
                # Run due checks
                results = await self.run_due_checks()
                
                # Log summary
                healthy = sum(1 for r in results if r.status == HealthStatus.HEALTHY)
                warning = sum(1 for r in results if r.status == HealthStatus.WARNING)
                critical = sum(1 for r in results if r.status == HealthStatus.CRITICAL)
                
                if results:
                    print(
                        f"[{datetime.now().isoformat()}] "
                        f"Ran {len(results)} checks: "
                        f"{healthy} healthy, {warning} warning, {critical} critical"
                    )
                
                # Wait for minimum interval
                min_interval = min(c.interval_seconds for c in self.config.checks)
                await asyncio.sleep(min_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in polling loop: {e}")
                await asyncio.sleep(10)  # Wait before retrying
    
    def stop_polling(self) -> None:
        """Stop the polling loop."""
        self._running = False
    
    async def get_summary(self) -> MonitoringSummary:
        """Get current monitoring summary."""
        return self.storage.get_summary(hours=24)
    
    async def cleanup(self) -> Dict[str, int]:
        """Run retention cleanup."""
        return self.storage.cleanup_old_data()
