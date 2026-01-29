"""
Splunk REST API client.

Provides async methods for log search and error rate analysis.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from monitoring_mcp.auth import get_auth_provider
from monitoring_mcp.config import get_config
from monitoring_mcp.models import (
    HealthStatus,
    SplunkLogEntry,
    SplunkSearchResult,
)

logger = logging.getLogger(__name__)


class SplunkClient:
    """Async client for Splunk REST API."""
    
    def __init__(self):
        self.config = get_config().splunk
        self.thresholds = get_config().thresholds
        self.auth = get_auth_provider("splunk")
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                verify=self.config.verify_ssl,
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
    ) -> Dict[str, Any]:
        """Make authenticated request to Splunk API."""
        client = await self._get_client()
        headers = await self.auth.get_headers()
        
        # Splunk API returns XML by default, request JSON
        headers["Accept"] = "application/json"
        
        response = await client.request(
            method,
            endpoint,
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()
        
        return response.json()
    
    async def search(
        self,
        query: str,
        time_range: str = "-1h",
        max_results: int = 100,
        output_mode: str = "json",
    ) -> SplunkSearchResult:
        """
        Execute a Splunk search query.
        
        Args:
            query: SPL (Splunk Processing Language) query
            time_range: Relative time range (e.g., "-1h", "-15m", "-1d")
            max_results: Maximum results to return
            output_mode: Output format
            
        Returns:
            SplunkSearchResult with events
        """
        logger.info(f"Executing Splunk search: {query[:100]}...")
        
        # Create search job
        search_query = query if query.startswith("search") else f"search {query}"
        
        try:
            # Submit search job
            job_response = await self._request(
                "POST",
                "/services/search/jobs",
                data={
                    "search": search_query,
                    "earliest_time": time_range,
                    "latest_time": "now",
                    "output_mode": output_mode,
                    "max_count": max_results,
                },
            )
            
            job_sid = job_response.get("sid")
            if not job_sid:
                raise ValueError("No job SID returned from Splunk")
            
            # Wait for job completion (poll status)
            await self._wait_for_job(job_sid)
            
            # Get results
            results_response = await self._request(
                "GET",
                f"/services/search/jobs/{job_sid}/results",
                params={"output_mode": "json", "count": max_results},
            )
            
            # Parse results
            events = []
            raw_results = results_response.get("results", [])
            
            for result in raw_results:
                events.append(SplunkLogEntry(
                    time=result.get("_time", ""),
                    source=result.get("source", ""),
                    sourcetype=result.get("sourcetype", ""),
                    host=result.get("host", ""),
                    raw=result.get("_raw", ""),
                    fields={k: v for k, v in result.items() if not k.startswith("_")},
                ))
            
            return SplunkSearchResult(
                status=HealthStatus.HEALTHY,
                query=query,
                result_count=len(events),
                events=events,
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Splunk search failed: {e}")
            return SplunkSearchResult(
                status=HealthStatus.CRITICAL,
                query=query,
                result_count=0,
                alerts=[f"Search failed: {str(e)}"],
            )
        except Exception as e:
            logger.error(f"Splunk search error: {e}")
            return SplunkSearchResult(
                status=HealthStatus.CRITICAL,
                query=query,
                result_count=0,
                alerts=[f"Search error: {str(e)}"],
            )
    
    async def _wait_for_job(self, job_sid: str, timeout: int = 60) -> None:
        """Wait for search job to complete."""
        import asyncio
        
        start_time = datetime.now()
        while True:
            status_response = await self._request(
                "GET",
                f"/services/search/jobs/{job_sid}",
                params={"output_mode": "json"},
            )
            
            entry = status_response.get("entry", [{}])[0]
            content = entry.get("content", {})
            dispatch_state = content.get("dispatchState", "")
            
            if dispatch_state == "DONE":
                return
            elif dispatch_state in ("FAILED", "FINALIZED"):
                raise ValueError(f"Search job failed: {dispatch_state}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                raise TimeoutError(f"Search job timed out after {timeout}s")
            
            await asyncio.sleep(1)
    
    async def get_error_rate(
        self,
        index: str = "main",
        service_name: Optional[str] = None,
        time_range: str = "-15m",
        error_codes: Optional[List[int]] = None,
    ) -> SplunkSearchResult:
        """
        Get error rate statistics for a service.
        
        Args:
            index: Splunk index to search
            service_name: Service name filter
            time_range: Relative time range
            error_codes: HTTP status codes to consider errors (default: 500, 502, 503, 504)
            
        Returns:
            SplunkSearchResult with error rate metrics
        """
        if error_codes is None:
            error_codes = [500, 502, 503, 504]
        
        error_codes_str = " OR ".join([f"status={code}" for code in error_codes])
        
        # Build query
        base_query = f'index="{index}"'
        if service_name:
            base_query += f' service="{service_name}"'
        
        # Query for total and error counts
        stats_query = f"""
            {base_query}
            | stats count as total_requests, 
                    count(eval({error_codes_str})) as error_count
            | eval error_rate = round(error_count/total_requests*100, 2)
        """
        
        try:
            result = await self.search(stats_query, time_range=time_range, max_results=1)
            
            # Extract stats from first result
            if result.events:
                fields = result.events[0].fields
                total_requests = int(fields.get("total_requests", 0))
                error_count = int(fields.get("error_count", 0))
                error_rate = float(fields.get("error_rate", 0))
                
                result.total_requests = total_requests
                result.error_count = error_count
                result.error_rate = error_rate
                
                # Check thresholds
                if error_rate >= self.thresholds.error_rate_critical:
                    result.status = HealthStatus.CRITICAL
                    result.alerts.append(
                        f"Critical: Error rate {error_rate:.2f}% exceeds {self.thresholds.error_rate_critical}%"
                    )
                elif error_rate >= self.thresholds.error_rate_warning:
                    result.status = HealthStatus.WARNING
                    result.alerts.append(
                        f"Warning: Error rate {error_rate:.2f}% exceeds {self.thresholds.error_rate_warning}%"
                    )
                else:
                    result.status = HealthStatus.HEALTHY
            
            # Get error breakdown by status code
            breakdown_query = f"""
                {base_query} ({error_codes_str})
                | stats count by status
            """
            breakdown_result = await self.search(breakdown_query, time_range=time_range)
            
            error_breakdown = {}
            for event in breakdown_result.events:
                status = event.fields.get("status")
                count = int(event.fields.get("count", 0))
                if status:
                    error_breakdown[status] = count
            
            result.error_breakdown = error_breakdown
            
            return result
            
        except Exception as e:
            logger.error(f"Error rate check failed: {e}")
            return SplunkSearchResult(
                status=HealthStatus.CRITICAL,
                query=stats_query,
                result_count=0,
                alerts=[f"Error rate check failed: {str(e)}"],
            )
    
    async def search_errors(
        self,
        index: str = "main",
        service_name: Optional[str] = None,
        time_range: str = "-15m",
        error_pattern: str = "error OR exception OR fail",
        max_results: int = 50,
    ) -> SplunkSearchResult:
        """
        Search for error logs.
        
        Args:
            index: Splunk index
            service_name: Service name filter
            time_range: Relative time range
            error_pattern: Search pattern for errors
            max_results: Maximum results
            
        Returns:
            SplunkSearchResult with error logs
        """
        query = f'index="{index}" ({error_pattern})'
        if service_name:
            query += f' service="{service_name}"'
        
        query += " | sort -_time"
        
        result = await self.search(query, time_range=time_range, max_results=max_results)
        
        if result.result_count > 0:
            result.status = HealthStatus.WARNING
            result.alerts.append(f"Found {result.result_count} error logs")
        
        return result
