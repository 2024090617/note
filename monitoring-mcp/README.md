# Monitoring MCP Server

A Model Context Protocol (MCP) server providing tools for infrastructure monitoring across multiple platforms:

- **Splunk** - Log search and analysis
- **AppDynamics** - Application performance metrics (JVM, response times, errors)
- **Kafka** - Consumer lag and broker health
- **MongoDB** - Server status and replica set health

## Features

- 🔧 **Unified API** - Single MCP interface for all monitoring tools
- 🔐 **AuthProvider Abstraction** - Supports tokens, OAuth, SASL, connection strings
- ⚡ **Async Operations** - Non-blocking API calls with httpx/aiokafka/motor
- 📊 **Structured Output** - Pydantic models for all responses
- 🔄 **Threshold Checks** - Built-in health evaluation against thresholds

## Installation

```bash
# From source
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and configure your credentials:

```bash
cp .env.example .env
# Edit .env with your API keys and endpoints
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SPLUNK_BASE_URL` | Splunk REST API endpoint | For Splunk |
| `SPLUNK_TOKEN` | Splunk HEC token | For Splunk |
| `APPDYNAMICS_BASE_URL` | AppDynamics controller URL | For AppD |
| `APPDYNAMICS_API_CLIENT_NAME` | OAuth client name | For AppD |
| `APPDYNAMICS_API_CLIENT_SECRET` | OAuth client secret | For AppD |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker list | For Kafka |
| `MONGODB_URI` | MongoDB connection string | For MongoDB |

## Usage

### Run MCP Server

```bash
# Start the MCP server
monitoring-mcp

# Or with Python
python -m monitoring_mcp.server
```

### Configure in Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "monitoring": {
      "command": "monitoring-mcp",
      "env": {
        "SPLUNK_BASE_URL": "https://your-splunk.com:8089",
        "SPLUNK_TOKEN": "your-token",
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:9092",
        "MONGODB_URI": "mongodb://localhost:27017"
      }
    }
  }
}
```

## Available Tools

### Splunk Tools

#### `search_splunk_logs`
Search Splunk logs with SPL query.

```python
{
    "query": "index=main error status=500",
    "time_range": "-1h",  # relative time
    "max_results": 100
}
```

#### `get_splunk_error_rate`
Get error rate statistics for a service.

```python
{
    "index": "main",
    "service_name": "payment-api",
    "time_range": "-15m",
    "error_codes": [500, 502, 503]
}
```

### AppDynamics Tools

#### `get_jvm_metrics`
Get JVM metrics for an application tier.

```python
{
    "application_name": "MyApp",
    "tier_name": "WebTier",
    "duration_minutes": 15
}
```

Returns: heap usage, GC time, thread counts

#### `get_business_transaction_health`
Get business transaction response times and error rates.

```python
{
    "application_name": "MyApp",
    "bt_name": "checkout",  # optional, all BTs if omitted
    "duration_minutes": 15
}
```

### Kafka Tools

#### `check_kafka_lag`
Check consumer group lag for topics.

```python
{
    "consumer_group": "my-consumer-group",
    "topics": ["orders", "events"],  # optional, all topics if omitted
}
```

Returns: lag per partition, total lag, threshold status

#### `get_kafka_broker_health`
Get Kafka cluster and broker status.

```python
{}  # No parameters, checks all brokers
```

### MongoDB Tools

#### `get_mongodb_status`
Get MongoDB server status and metrics.

```python
{
    "database": "admin"  # optional
}
```

Returns: connections, operations/sec, memory usage, replication lag

#### `check_mongodb_replica_health`
Check replica set health and member status.

```python
{}
```

## Response Models

All tools return structured responses with:

```python
{
    "status": "healthy" | "warning" | "critical",
    "metrics": { ... },
    "alerts": ["Alert message 1", ...],
    "timestamp": "2024-01-15T10:30:00Z"
}
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
ruff check src/ --fix
```

## Architecture

```
monitoring-mcp/
├── src/monitoring_mcp/
│   ├── __init__.py
│   ├── config.py       # Pydantic settings
│   ├── auth.py         # AuthProvider abstraction
│   ├── models.py       # Response models
│   ├── clients/        # API clients
│   │   ├── splunk.py
│   │   ├── appdynamics.py
│   │   ├── kafka.py
│   │   └── mongodb.py
│   ├── tools.py        # MCP tool definitions
│   └── server.py       # MCP server
└── tests/
```

## License

MIT
