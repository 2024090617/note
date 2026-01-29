"""
Microsoft Teams notifier for monitoring alerts.

Sends alert notifications to Teams channels via webhooks.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from .config import TeamsConfig
from .models import Alert, AlertSeverity, HealthStatus, MonitoringSummary


class TeamsNotifier:
    """
    Microsoft Teams notification sender.
    
    Features:
    - Adaptive card format for rich notifications
    - Rate limiting to prevent spam
    - Severity-based filtering
    - Batching support for multiple alerts
    """
    
    # Color mapping for severity
    SEVERITY_COLORS = {
        AlertSeverity.INFO: "#0078D4",      # Blue
        AlertSeverity.WARNING: "#FFA500",   # Orange
        AlertSeverity.CRITICAL: "#D13438",  # Red
    }
    
    STATUS_COLORS = {
        HealthStatus.HEALTHY: "#107C10",    # Green
        HealthStatus.WARNING: "#FFA500",    # Orange
        HealthStatus.CRITICAL: "#D13438",   # Red
        HealthStatus.ERROR: "#D13438",      # Red
        HealthStatus.UNKNOWN: "#808080",    # Gray
    }
    
    def __init__(self, config: TeamsConfig):
        """Initialize with Teams configuration."""
        self.config = config
        self._last_sent: Dict[str, datetime] = {}  # For rate limiting
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self) -> "TeamsNotifier":
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _should_send(self, alert: Alert) -> bool:
        """Check if alert should be sent based on severity and rate limiting."""
        # Check severity threshold
        severity_order = [AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL]
        min_idx = severity_order.index(self.config.min_severity)
        alert_idx = severity_order.index(alert.severity)
        
        if alert_idx < min_idx:
            return False
        
        # Check rate limiting
        key = f"{alert.check_name}:{alert.metric_name}:{alert.severity.value}"
        last_sent = self._last_sent.get(key)
        
        if last_sent:
            elapsed = (datetime.now() - last_sent).total_seconds()
            if elapsed < self.config.rate_limit_seconds:
                return False
        
        return True
    
    def _mark_sent(self, alert: Alert) -> None:
        """Mark alert as sent for rate limiting."""
        key = f"{alert.check_name}:{alert.metric_name}:{alert.severity.value}"
        self._last_sent[key] = datetime.now()
    
    def _build_alert_card(self, alert: Alert) -> Dict[str, Any]:
        """Build adaptive card for a single alert."""
        color = self.SEVERITY_COLORS.get(alert.severity, "#808080")
        
        # Build facts section
        facts = [
            {"title": "Service", "value": alert.service},
            {"title": "Check", "value": alert.check_name},
            {"title": "Metric", "value": alert.metric_name},
            {"title": "Current Value", "value": f"{alert.current_value:.2f}"},
            {"title": "Threshold", "value": f"{alert.threshold_value:.2f}"},
            {"title": "Time", "value": alert.created_at.strftime("%Y-%m-%d %H:%M:%S")},
        ]
        
        # Build card
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "Container",
                                "style": "emphasis",
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": f"🚨 {alert.severity.value.upper()}: {alert.title}",
                                        "weight": "bolder",
                                        "size": "large",
                                        "color": "attention" if alert.severity == AlertSeverity.CRITICAL else "warning",
                                    }
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": alert.message,
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": facts,
                            },
                        ],
                        "msteams": {
                            "width": "Full",
                        },
                    },
                }
            ],
        }
        
        return card
    
    def _build_summary_card(self, summary: MonitoringSummary) -> Dict[str, Any]:
        """Build adaptive card for monitoring summary."""
        status_emoji = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.WARNING: "⚠️",
            HealthStatus.CRITICAL: "🔴",
            HealthStatus.ERROR: "❌",
            HealthStatus.UNKNOWN: "❓",
        }
        
        # Build status facts
        facts = [
            {"title": "Overall Status", "value": f"{status_emoji[summary.overall_status]} {summary.overall_status.value.upper()}"},
            {"title": "Total Checks", "value": str(summary.total_checks)},
            {"title": "Healthy", "value": f"✅ {summary.healthy_checks}"},
            {"title": "Warning", "value": f"⚠️ {summary.warning_checks}"},
            {"title": "Critical", "value": f"🔴 {summary.critical_checks}"},
            {"title": "Active Alerts", "value": str(summary.active_alerts)},
        ]
        
        # Build service status
        service_items = []
        for service, status in summary.service_status.items():
            emoji = status_emoji.get(status, "❓")
            service_items.append({
                "type": "TextBlock",
                "text": f"{emoji} **{service}**: {status.value}",
            })
        
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "📊 Monitoring Summary",
                                "weight": "bolder",
                                "size": "large",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Report generated at {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
                                "isSubtle": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": facts,
                            },
                            {
                                "type": "TextBlock",
                                "text": "**Service Status**",
                                "weight": "bolder",
                            },
                            *service_items,
                        ],
                        "msteams": {
                            "width": "Full",
                        },
                    },
                }
            ],
        }
        
        return card
    
    def _build_recovery_card(self, alert: Alert) -> Dict[str, Any]:
        """Build adaptive card for alert recovery."""
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"✅ RESOLVED: {alert.title}",
                                "weight": "bolder",
                                "size": "large",
                                "color": "good",
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Alert for {alert.check_name} ({alert.metric_name}) has been resolved.",
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Service", "value": alert.service},
                                    {"title": "Check", "value": alert.check_name},
                                    {"title": "Duration", "value": self._format_duration(alert)},
                                    {"title": "Resolved At", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                                ],
                            },
                        ],
                        "msteams": {
                            "width": "Full",
                        },
                    },
                }
            ],
        }
        
        return card
    
    def _format_duration(self, alert: Alert) -> str:
        """Format alert duration."""
        if alert.resolved_at:
            duration = alert.resolved_at - alert.created_at
        else:
            duration = datetime.now() - alert.created_at
        
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    async def send_alert(self, alert: Alert) -> bool:
        """
        Send an alert notification to Teams.
        
        Returns True if sent successfully, False if skipped or failed.
        """
        if not self.config.webhook_url:
            return False
        
        if not self._should_send(alert):
            return False
        
        card = self._build_alert_card(alert)
        
        try:
            if not self._client:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.config.webhook_url,
                        json=card,
                    )
            else:
                response = await self._client.post(
                    self.config.webhook_url,
                    json=card,
                )
            
            if response.status_code == 200:
                self._mark_sent(alert)
                return True
            else:
                return False
                
        except Exception as e:
            # Log error but don't raise
            print(f"Failed to send Teams notification: {e}")
            return False
    
    async def send_recovery(self, alert: Alert) -> bool:
        """Send a recovery notification for a resolved alert."""
        if not self.config.webhook_url:
            return False
        
        card = self._build_recovery_card(alert)
        
        try:
            if not self._client:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.config.webhook_url,
                        json=card,
                    )
            else:
                response = await self._client.post(
                    self.config.webhook_url,
                    json=card,
                )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"Failed to send Teams recovery notification: {e}")
            return False
    
    async def send_summary(self, summary: MonitoringSummary) -> bool:
        """Send a monitoring summary to Teams."""
        if not self.config.webhook_url:
            return False
        
        card = self._build_summary_card(summary)
        
        try:
            if not self._client:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        self.config.webhook_url,
                        json=card,
                    )
            else:
                response = await self._client.post(
                    self.config.webhook_url,
                    json=card,
                )
            
            return response.status_code == 200
            
        except Exception as e:
            print(f"Failed to send Teams summary: {e}")
            return False
    
    async def send_alerts_batch(self, alerts: List[Alert]) -> Dict[str, int]:
        """
        Send multiple alerts.
        
        Returns dict with counts of sent, skipped, and failed.
        """
        results = {"sent": 0, "skipped": 0, "failed": 0}
        
        for alert in alerts:
            if not self._should_send(alert):
                results["skipped"] += 1
                continue
            
            success = await self.send_alert(alert)
            if success:
                results["sent"] += 1
            else:
                results["failed"] += 1
            
            # Small delay between messages to avoid rate limits
            await asyncio.sleep(0.5)
        
        return results
    
    async def test_connection(self) -> bool:
        """Test the webhook connection with a test message."""
        if not self.config.webhook_url:
            return False
        
        test_card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "🔔 Monitoring Agent Connected",
                                "weight": "bolder",
                                "size": "medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": "This is a test message to verify the Teams webhook connection.",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                "isSubtle": True,
                            },
                        ],
                    },
                }
            ],
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.config.webhook_url,
                    json=test_card,
                )
                return response.status_code == 200
        except Exception:
            return False
