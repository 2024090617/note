"""
AppDynamics REST API client.

Provides async methods for JVM metrics and business transaction health.
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from monitoring_mcp.auth import get_auth_provider
from monitoring_mcp.config import get_config
from monitoring_mcp.models import (
    AppDynamicsResult,
    BusinessTransactionMetrics,
    HealthStatus,
    JvmMetrics,
)

logger = logging.getLogger(__name__)


class AppDynamicsClient:
    """Async client for AppDynamics REST API."""
    
    def __init__(self):
        self.config = get_config().appdynamics
        self.thresholds = get_config().thresholds
        self.auth = get_auth_provider("appdynamics")
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
            )
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> Any:
        """Make authenticated request to AppDynamics API."""
        client = await self._get_client()
        headers = await self.auth.get_headers()
        
        response = await client.request(
            method,
            endpoint,
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()
        
        return response.json()
    
    async def _get_metric_data(
        self,
        application_name: str,
        metric_path: str,
        duration_minutes: int = 15,
        rollup: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get metric data from AppDynamics.
        
        Args:
            application_name: Application name
            metric_path: Metric path (e.g., "Application Infrastructure Performance|*|JVM|Memory|Heap|Current Usage (MB)")
            duration_minutes: Duration in minutes
            rollup: Whether to rollup data
            
        Returns:
            List of metric data points
        """
        endpoint = f"/controller/rest/applications/{application_name}/metric-data"
        
        params = {
            "metric-path": metric_path,
            "time-range-type": "BEFORE_NOW",
            "duration-in-mins": duration_minutes,
            "rollup": str(rollup).lower(),
            "output": "JSON",
        }
        
        data = await self._request("GET", endpoint, params=params)
        return data if isinstance(data, list) else []
    
    async def get_jvm_metrics(
        self,
        application_name: str,
        tier_name: Optional[str] = None,
        duration_minutes: int = 15,
    ) -> AppDynamicsResult:
        """
        Get JVM metrics for an application tier.
        
        Args:
            application_name: Application name
            tier_name: Tier name (optional, uses wildcard if not specified)
            duration_minutes: Duration in minutes
            
        Returns:
            AppDynamicsResult with JVM metrics
        """
        logger.info(f"Getting JVM metrics for {application_name}/{tier_name or '*'}")
        
        tier_filter = tier_name or "*"
        result = AppDynamicsResult(
            application_name=application_name,
            tier_name=tier_name,
            duration_minutes=duration_minutes,
            status=HealthStatus.HEALTHY,
        )
        
        try:
            # Heap metrics
            heap_used_data = await self._get_metric_data(
                application_name,
                f"Application Infrastructure Performance|{tier_filter}|JVM|Memory|Heap|Current Usage (MB)",
                duration_minutes,
            )
            
            heap_max_data = await self._get_metric_data(
                application_name,
                f"Application Infrastructure Performance|{tier_filter}|JVM|Memory|Heap|Max Available (MB)",
                duration_minutes,
            )
            
            # GC metrics
            gc_time_data = await self._get_metric_data(
                application_name,
                f"Application Infrastructure Performance|{tier_filter}|JVM|Garbage Collection|GC Time Spent Per Min (ms)",
                duration_minutes,
            )
            
            gc_count_data = await self._get_metric_data(
                application_name,
                f"Application Infrastructure Performance|{tier_filter}|JVM|Garbage Collection|Number of Major Collections Per Min",
                duration_minutes,
            )
            
            # Thread metrics
            thread_count_data = await self._get_metric_data(
                application_name,
                f"Application Infrastructure Performance|{tier_filter}|JVM|Threads|Current No. of Threads",
                duration_minutes,
            )
            
            # CPU metrics
            cpu_data = await self._get_metric_data(
                application_name,
                f"Application Infrastructure Performance|{tier_filter}|JVM|Process CPU Usage %",
                duration_minutes,
            )
            
            # Extract values
            heap_used = self._extract_metric_value(heap_used_data)
            heap_max = self._extract_metric_value(heap_max_data)
            heap_usage_percent = (heap_used / heap_max * 100) if heap_max > 0 else 0
            
            jvm = JvmMetrics(
                heap_used_mb=heap_used,
                heap_max_mb=heap_max,
                heap_usage_percent=round(heap_usage_percent, 2),
                gc_time_ms=self._extract_metric_value(gc_time_data),
                gc_count=int(self._extract_metric_value(gc_count_data)),
                thread_count=int(self._extract_metric_value(thread_count_data)),
                cpu_usage_percent=self._extract_metric_value(cpu_data),
            )
            
            result.jvm = jvm
            
            # Check thresholds
            if heap_usage_percent >= self.thresholds.jvm_heap_usage_critical:
                result.status = HealthStatus.CRITICAL
                result.alerts.append(
                    f"Critical: JVM heap usage {heap_usage_percent:.1f}% exceeds {self.thresholds.jvm_heap_usage_critical}%"
                )
            elif heap_usage_percent >= self.thresholds.jvm_heap_usage_warning:
                result.status = HealthStatus.WARNING
                result.alerts.append(
                    f"Warning: JVM heap usage {heap_usage_percent:.1f}% exceeds {self.thresholds.jvm_heap_usage_warning}%"
                )
            
            return result
            
        except httpx.HTTPStatusError as e:
            logger.error(f"AppDynamics API error: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append(f"API error: {str(e)}")
            return result
        except Exception as e:
            logger.error(f"JVM metrics error: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append(f"Error: {str(e)}")
            return result
    
    async def get_business_transaction_health(
        self,
        application_name: str,
        bt_name: Optional[str] = None,
        duration_minutes: int = 15,
    ) -> AppDynamicsResult:
        """
        Get business transaction metrics.
        
        Args:
            application_name: Application name
            bt_name: Business transaction name (optional, gets all if not specified)
            duration_minutes: Duration in minutes
            
        Returns:
            AppDynamicsResult with transaction metrics
        """
        logger.info(f"Getting BT health for {application_name}/{bt_name or 'all'}")
        
        result = AppDynamicsResult(
            application_name=application_name,
            duration_minutes=duration_minutes,
            status=HealthStatus.HEALTHY,
        )
        
        try:
            # Get list of business transactions
            bt_endpoint = f"/controller/rest/applications/{application_name}/business-transactions"
            bt_list = await self._request("GET", bt_endpoint, params={"output": "JSON"})
            
            # Filter by name if specified
            if bt_name:
                bt_list = [bt for bt in bt_list if bt.get("name") == bt_name]
            
            transactions = []
            overall_error_rate = 0
            overall_response_time = 0
            total_calls = 0
            
            for bt in bt_list[:20]:  # Limit to 20 BTs
                bt_id = bt.get("id")
                name = bt.get("name", "Unknown")
                
                # Get metrics for this BT
                cpm_data = await self._get_metric_data(
                    application_name,
                    f"Business Transaction Performance|Business Transactions|{bt.get('tierName', '*')}|{name}|Calls per Minute",
                    duration_minutes,
                )
                
                response_time_data = await self._get_metric_data(
                    application_name,
                    f"Business Transaction Performance|Business Transactions|{bt.get('tierName', '*')}|{name}|Average Response Time (ms)",
                    duration_minutes,
                )
                
                error_rate_data = await self._get_metric_data(
                    application_name,
                    f"Business Transaction Performance|Business Transactions|{bt.get('tierName', '*')}|{name}|Errors per Minute",
                    duration_minutes,
                )
                
                calls_per_min = self._extract_metric_value(cpm_data)
                avg_response_time = self._extract_metric_value(response_time_data)
                errors_per_min = self._extract_metric_value(error_rate_data)
                error_rate = (errors_per_min / calls_per_min * 100) if calls_per_min > 0 else 0
                
                bt_metrics = BusinessTransactionMetrics(
                    name=name,
                    calls_per_minute=calls_per_min,
                    avg_response_time_ms=avg_response_time,
                    error_rate=round(error_rate, 2),
                    errors_per_minute=errors_per_min,
                )
                
                transactions.append(bt_metrics)
                
                # Accumulate for overall stats
                if calls_per_min > 0:
                    total_calls += calls_per_min
                    overall_response_time += avg_response_time * calls_per_min
                    overall_error_rate += errors_per_min
                
                # Check thresholds per BT
                if error_rate >= self.thresholds.error_rate_critical:
                    result.status = HealthStatus.CRITICAL
                    result.alerts.append(f"Critical: {name} error rate {error_rate:.2f}%")
                elif error_rate >= self.thresholds.error_rate_warning:
                    if result.status != HealthStatus.CRITICAL:
                        result.status = HealthStatus.WARNING
                    result.alerts.append(f"Warning: {name} error rate {error_rate:.2f}%")
                
                if avg_response_time >= self.thresholds.response_time_critical:
                    result.status = HealthStatus.CRITICAL
                    result.alerts.append(f"Critical: {name} response time {avg_response_time:.0f}ms")
                elif avg_response_time >= self.thresholds.response_time_warning:
                    if result.status != HealthStatus.CRITICAL:
                        result.status = HealthStatus.WARNING
                    result.alerts.append(f"Warning: {name} response time {avg_response_time:.0f}ms")
            
            result.transactions = transactions
            
            # Calculate overall metrics
            if total_calls > 0:
                result.overall_error_rate = round(overall_error_rate / total_calls * 100, 2)
                result.overall_response_time = round(overall_response_time / total_calls, 2)
            
            return result
            
        except Exception as e:
            logger.error(f"BT health error: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append(f"Error: {str(e)}")
            return result
    
    def _extract_metric_value(
        self,
        metric_data: List[Dict[str, Any]],
        value_key: str = "value",
    ) -> float:
        """Extract metric value from AppDynamics response."""
        if not metric_data:
            return 0.0
        
        # Get the first metric path's data
        for metric in metric_data:
            values = metric.get("metricValues", [])
            if values:
                # Return the most recent value
                return float(values[-1].get(value_key, 0))
        
        return 0.0
