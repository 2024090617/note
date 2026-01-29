"""
MCP tool definitions for monitoring services.

Defines all available monitoring tools with their schemas and handlers.
"""

import logging
from typing import Any, Dict, List, Optional

from mcp.types import Tool, TextContent

from monitoring_mcp.clients import (
    AppDynamicsClient,
    KafkaClient,
    MongoDBClient,
    SplunkClient,
)
from monitoring_mcp.config import get_config
from monitoring_mcp.models import HealthStatus

logger = logging.getLogger(__name__)


# =============================================================================
# Tool Definitions
# =============================================================================

TOOLS: List[Tool] = [
    # Splunk Tools
    Tool(
        name="search_splunk_logs",
        description="Search Splunk logs using SPL (Splunk Processing Language). Returns matching log entries with timestamps, sources, and extracted fields.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SPL query (e.g., 'index=main error status=500'). The 'search' prefix is optional.",
                },
                "time_range": {
                    "type": "string",
                    "description": "Relative time range (e.g., '-1h', '-15m', '-1d'). Default: '-1h'",
                    "default": "-1h",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return. Default: 100",
                    "default": 100,
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="get_splunk_error_rate",
        description="Get HTTP error rate statistics for a service. Returns total requests, error count, error rate percentage, and breakdown by status code.",
        inputSchema={
            "type": "object",
            "properties": {
                "index": {
                    "type": "string",
                    "description": "Splunk index to search. Default: 'main'",
                    "default": "main",
                },
                "service_name": {
                    "type": "string",
                    "description": "Service name to filter (optional). Matches 'service' field in logs.",
                },
                "time_range": {
                    "type": "string",
                    "description": "Relative time range. Default: '-15m'",
                    "default": "-15m",
                },
                "error_codes": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "HTTP status codes to consider errors. Default: [500, 502, 503, 504]",
                },
            },
            "required": [],
        },
    ),
    
    # AppDynamics Tools
    Tool(
        name="get_jvm_metrics",
        description="Get JVM metrics from AppDynamics: heap usage, GC time, thread count, CPU usage. Checks against configured thresholds.",
        inputSchema={
            "type": "object",
            "properties": {
                "application_name": {
                    "type": "string",
                    "description": "AppDynamics application name",
                },
                "tier_name": {
                    "type": "string",
                    "description": "Tier name (optional, uses wildcard if not specified)",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes for metrics. Default: 15",
                    "default": 15,
                },
            },
            "required": ["application_name"],
        },
    ),
    Tool(
        name="get_business_transaction_health",
        description="Get business transaction metrics from AppDynamics: calls/minute, response time, error rate. Identifies slow or failing transactions.",
        inputSchema={
            "type": "object",
            "properties": {
                "application_name": {
                    "type": "string",
                    "description": "AppDynamics application name",
                },
                "bt_name": {
                    "type": "string",
                    "description": "Business transaction name (optional, gets all if not specified)",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Duration in minutes for metrics. Default: 15",
                    "default": 15,
                },
            },
            "required": ["application_name"],
        },
    ),
    
    # Kafka Tools
    Tool(
        name="check_kafka_lag",
        description="Check Kafka consumer group lag. Returns lag per partition and total lag. Alerts if lag exceeds thresholds (warning: 100, critical: 1000).",
        inputSchema={
            "type": "object",
            "properties": {
                "consumer_group": {
                    "type": "string",
                    "description": "Kafka consumer group name",
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Topics to check (optional, checks all subscribed topics if not specified)",
                },
            },
            "required": ["consumer_group"],
        },
    ),
    Tool(
        name="get_kafka_broker_health",
        description="Get Kafka cluster health: broker count, controller status, topic/partition counts. Warns if single broker or no controller.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    
    # MongoDB Tools
    Tool(
        name="get_mongodb_status",
        description="Get MongoDB server status: connections, operations/sec, memory usage, uptime. Checks connection count against thresholds.",
        inputSchema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name for status command. Default: 'admin'",
                    "default": "admin",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="check_mongodb_replica_health",
        description="Check MongoDB replica set health: member states, replication lag, primary/secondary status. Critical if no primary or unhealthy members.",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    
    # Utility Tools
    Tool(
        name="get_monitoring_config",
        description="Get current monitoring configuration including enabled services, thresholds, and connection status (secrets masked).",
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
]


# =============================================================================
# Tool Handlers
# =============================================================================

async def handle_search_splunk_logs(arguments: Dict[str, Any]) -> str:
    """Handle search_splunk_logs tool call."""
    client = SplunkClient()
    try:
        result = await client.search(
            query=arguments["query"],
            time_range=arguments.get("time_range", "-1h"),
            max_results=arguments.get("max_results", 100),
        )
        return _format_result(result)
    finally:
        await client.close()


async def handle_get_splunk_error_rate(arguments: Dict[str, Any]) -> str:
    """Handle get_splunk_error_rate tool call."""
    client = SplunkClient()
    try:
        result = await client.get_error_rate(
            index=arguments.get("index", "main"),
            service_name=arguments.get("service_name"),
            time_range=arguments.get("time_range", "-15m"),
            error_codes=arguments.get("error_codes"),
        )
        return _format_result(result)
    finally:
        await client.close()


async def handle_get_jvm_metrics(arguments: Dict[str, Any]) -> str:
    """Handle get_jvm_metrics tool call."""
    client = AppDynamicsClient()
    try:
        result = await client.get_jvm_metrics(
            application_name=arguments["application_name"],
            tier_name=arguments.get("tier_name"),
            duration_minutes=arguments.get("duration_minutes", 15),
        )
        return _format_result(result)
    finally:
        await client.close()


async def handle_get_business_transaction_health(arguments: Dict[str, Any]) -> str:
    """Handle get_business_transaction_health tool call."""
    client = AppDynamicsClient()
    try:
        result = await client.get_business_transaction_health(
            application_name=arguments["application_name"],
            bt_name=arguments.get("bt_name"),
            duration_minutes=arguments.get("duration_minutes", 15),
        )
        return _format_result(result)
    finally:
        await client.close()


async def handle_check_kafka_lag(arguments: Dict[str, Any]) -> str:
    """Handle check_kafka_lag tool call."""
    client = KafkaClient()
    try:
        result = await client.check_consumer_lag(
            consumer_group=arguments["consumer_group"],
            topics=arguments.get("topics"),
        )
        return _format_result(result)
    finally:
        await client.close()


async def handle_get_kafka_broker_health(arguments: Dict[str, Any]) -> str:
    """Handle get_kafka_broker_health tool call."""
    client = KafkaClient()
    try:
        result = await client.get_broker_health()
        return _format_result(result)
    finally:
        await client.close()


async def handle_get_mongodb_status(arguments: Dict[str, Any]) -> str:
    """Handle get_mongodb_status tool call."""
    client = MongoDBClient()
    try:
        result = await client.get_server_status(
            database=arguments.get("database"),
        )
        return _format_result(result)
    finally:
        await client.close()


async def handle_check_mongodb_replica_health(arguments: Dict[str, Any]) -> str:
    """Handle check_mongodb_replica_health tool call."""
    client = MongoDBClient()
    try:
        result = await client.check_replica_health()
        return _format_result(result)
    finally:
        await client.close()


async def handle_get_monitoring_config(arguments: Dict[str, Any]) -> str:
    """Handle get_monitoring_config tool call."""
    config = get_config()
    return _format_dict(config.to_dict())


# =============================================================================
# Tool Handler Registry
# =============================================================================

TOOL_HANDLERS = {
    "search_splunk_logs": handle_search_splunk_logs,
    "get_splunk_error_rate": handle_get_splunk_error_rate,
    "get_jvm_metrics": handle_get_jvm_metrics,
    "get_business_transaction_health": handle_get_business_transaction_health,
    "check_kafka_lag": handle_check_kafka_lag,
    "get_kafka_broker_health": handle_get_kafka_broker_health,
    "get_mongodb_status": handle_get_mongodb_status,
    "check_mongodb_replica_health": handle_check_mongodb_replica_health,
    "get_monitoring_config": handle_get_monitoring_config,
}


async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Call a monitoring tool by name.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        
    Returns:
        List of TextContent with results
    """
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# =============================================================================
# Formatting Helpers
# =============================================================================

def _format_result(result) -> str:
    """Format a Pydantic model result as readable text."""
    lines = []
    
    # Status header
    status = getattr(result, "status", HealthStatus.UNKNOWN)
    status_emoji = {
        HealthStatus.HEALTHY: "✅",
        HealthStatus.WARNING: "⚠️",
        HealthStatus.CRITICAL: "🔴",
        HealthStatus.UNKNOWN: "❓",
    }.get(status, "❓")
    
    lines.append(f"## {status_emoji} Status: {status.value.upper()}")
    lines.append("")
    
    # Alerts
    alerts = getattr(result, "alerts", [])
    if alerts:
        lines.append("### Alerts")
        for alert in alerts:
            lines.append(f"- {alert}")
        lines.append("")
    
    # Service-specific formatting
    service = getattr(result, "service", "")
    
    if service == "splunk":
        lines.extend(_format_splunk_result(result))
    elif service == "appdynamics":
        lines.extend(_format_appdynamics_result(result))
    elif service == "kafka":
        lines.extend(_format_kafka_result(result))
    elif service == "mongodb":
        lines.extend(_format_mongodb_result(result))
    else:
        # Generic formatting
        lines.append("### Details")
        lines.append(f"```json\n{result.model_dump_json(indent=2)}\n```")
    
    return "\n".join(lines)


def _format_splunk_result(result) -> List[str]:
    """Format Splunk result."""
    lines = []
    
    lines.append("### Query Results")
    lines.append(f"- **Query**: `{result.query}`")
    lines.append(f"- **Results**: {result.result_count}")
    
    if result.total_requests is not None:
        lines.append("")
        lines.append("### Error Rate Metrics")
        lines.append(f"- **Total Requests**: {result.total_requests:,}")
        lines.append(f"- **Error Count**: {result.error_count:,}")
        lines.append(f"- **Error Rate**: {result.error_rate:.2f}%")
        
        if result.error_breakdown:
            lines.append("")
            lines.append("### Error Breakdown")
            for code, count in sorted(result.error_breakdown.items()):
                lines.append(f"- HTTP {code}: {count}")
    
    if result.events and len(result.events) <= 10:
        lines.append("")
        lines.append("### Sample Events")
        for event in result.events[:5]:
            lines.append(f"- [{event.time}] {event.raw[:200]}...")
    
    return lines


def _format_appdynamics_result(result) -> List[str]:
    """Format AppDynamics result."""
    lines = []
    
    lines.append("### Application Info")
    lines.append(f"- **Application**: {result.application_name}")
    if result.tier_name:
        lines.append(f"- **Tier**: {result.tier_name}")
    lines.append(f"- **Duration**: {result.duration_minutes} minutes")
    
    if result.jvm:
        jvm = result.jvm
        lines.append("")
        lines.append("### JVM Metrics")
        lines.append(f"- **Heap Usage**: {jvm.heap_used_mb:.1f} / {jvm.heap_max_mb:.1f} MB ({jvm.heap_usage_percent:.1f}%)")
        lines.append(f"- **GC Time**: {jvm.gc_time_ms:.1f} ms ({jvm.gc_count} collections)")
        lines.append(f"- **Threads**: {jvm.thread_count} (blocked: {jvm.thread_blocked})")
        lines.append(f"- **CPU Usage**: {jvm.cpu_usage_percent:.1f}%")
    
    if result.transactions:
        lines.append("")
        lines.append("### Business Transactions")
        for bt in result.transactions[:10]:
            lines.append(f"- **{bt.name}**: {bt.calls_per_minute:.1f} cpm, {bt.avg_response_time_ms:.0f}ms, {bt.error_rate:.2f}% errors")
    
    if result.overall_error_rate is not None:
        lines.append("")
        lines.append("### Overall Metrics")
        lines.append(f"- **Error Rate**: {result.overall_error_rate:.2f}%")
        lines.append(f"- **Avg Response Time**: {result.overall_response_time:.0f}ms")
    
    return lines


def _format_kafka_result(result) -> List[str]:
    """Format Kafka result."""
    lines = []
    
    # Consumer lag result
    if hasattr(result, "consumer_group"):
        lines.append("### Consumer Group")
        lines.append(f"- **Group**: {result.consumer_group}")
        lines.append(f"- **Total Lag**: {result.total_lag:,}")
        lines.append(f"- **Thresholds**: Warning={result.lag_threshold_warning}, Critical={result.lag_threshold_critical}")
        
        if result.topics:
            lines.append("")
            lines.append("### Topic Lag")
            for topic in result.topics:
                lines.append(f"- **{topic.topic}**: Total={topic.total_lag:,}, Max Partition={topic.max_partition_lag:,}")
    
    # Broker health result
    if hasattr(result, "brokers"):
        lines.append("### Cluster Info")
        lines.append(f"- **Brokers**: {result.broker_count}")
        lines.append(f"- **Controller**: Broker {result.controller_id}")
        lines.append(f"- **Topics**: {result.topic_count}")
        lines.append(f"- **Partitions**: {result.partition_count}")
        
        if result.brokers:
            lines.append("")
            lines.append("### Brokers")
            for broker in result.brokers:
                controller = " (controller)" if broker.is_controller else ""
                lines.append(f"- Broker {broker.broker_id}: {broker.host}:{broker.port}{controller}")
    
    return lines


def _format_mongodb_result(result) -> List[str]:
    """Format MongoDB result."""
    lines = []
    
    lines.append("### Server Info")
    lines.append(f"- **Host**: {result.host}")
    lines.append(f"- **Version**: {result.version}")
    lines.append(f"- **Uptime**: {result.uptime_seconds // 3600}h {(result.uptime_seconds % 3600) // 60}m")
    
    lines.append("")
    lines.append("### Connections")
    conn = result.connections
    lines.append(f"- **Current**: {conn.current} / {conn.available} available")
    lines.append(f"- **Active**: {conn.active}")
    lines.append(f"- **Total Created**: {conn.total_created:,}")
    
    lines.append("")
    lines.append("### Operations")
    ops = result.operations
    lines.append(f"- **Query**: {ops.query:,}")
    lines.append(f"- **Insert**: {ops.insert:,}")
    lines.append(f"- **Update**: {ops.update:,}")
    lines.append(f"- **Delete**: {ops.delete:,}")
    
    lines.append("")
    lines.append("### Memory")
    lines.append(f"- **Resident**: {result.resident_mb:.0f} MB")
    lines.append(f"- **Virtual**: {result.virtual_mb:.0f} MB")
    
    if result.is_replica_set:
        lines.append("")
        lines.append("### Replica Set")
        lines.append(f"- **Name**: {result.replica_set_name}")
        lines.append(f"- **Members**: {len(result.members)}")
        
        for member in result.members:
            role = "PRIMARY" if member.is_primary else "SECONDARY" if member.is_secondary else member.state_str
            health = "✅" if member.health == 1 else "🔴"
            lag = f" (lag: {member.lag_seconds}s)" if member.lag_seconds else ""
            lines.append(f"- {health} {member.name}: {role}{lag}")
    
    return lines


def _format_dict(data: Dict[str, Any]) -> str:
    """Format dictionary as readable text."""
    import json
    return f"```json\n{json.dumps(data, indent=2)}\n```"
