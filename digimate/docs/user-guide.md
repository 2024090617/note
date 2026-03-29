# User Guide — Digimate

How to install, configure, and use the digimate developer agent via Docker.

## Quick Start

```bash
# Pull the image (replace NEXUS_REGISTRY with your actual registry)
docker pull NEXUS_REGISTRY/digimate:latest

# Run a one-off task
docker run --rm \
  -e DIGIMATE_BACKEND=openai \
  -e DIGIMATE_API_BASE=http://host.docker.internal:8080/v1 \
  -e DIGIMATE_MODEL=gpt-4.1 \
  -v "$(pwd)":/workspace \
  NEXUS_REGISTRY/digimate:latest \
  "list all Python files in this project"
```

## Environment Variables

All configuration is done via `DIGIMATE_*` environment variables. Only set the ones you need — everything else uses sensible defaults.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DIGIMATE_BACKEND` | str | `copilot` | LLM backend: `copilot` or `openai` |
| `DIGIMATE_MODEL` | str | `gpt-4.1` | Model name to use |
| `DIGIMATE_API_BASE` | str | _(none)_ | API base URL for OpenAI-compatible backend |
| `DIGIMATE_API_KEY` | str | _(none)_ | API key (if required by backend) |
| `DIGIMATE_WORKDIR` | str | `.` (cwd) | Working directory inside the container |
| `DIGIMATE_MAX_ITERATIONS` | int | `20` | Max ReAct iterations per task |
| `DIGIMATE_CONTEXT_WINDOW` | int | `128000` | Context window size in tokens |
| `DIGIMATE_REQUEST_TIMEOUT` | int | `120` | LLM request timeout in seconds |
| `DIGIMATE_MCP_CONFIG` | str | _(none)_ | Path to MCP server config JSON (inside container) |
| `DIGIMATE_MEMORY_STRATEGY` | str | `claude-code` | Memory strategy: `claude-code` or `none` |
| `DIGIMATE_TRACE_STDERR` | bool | `true` | Show trace output on stderr |
| `DIGIMATE_TRACE_FILE` | bool | `true` | Write trace to `.digimate/log/` |
| `DIGIMATE_AUTO_COMPACT` | bool | `true` | Auto-compact session when context budget exceeded |
| `DIGIMATE_VERBOSE` | bool | `false` | Verbose output |

> **Bool values**: `1`, `true`, `yes` (case-insensitive) → true; anything else → false.

## Volume Mounts

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| Your project directory | `/workspace` | Agent reads/edits your files here |
| Persistent data directory | `/root/.digimate` | Agent memory, logs, cache (survives container restarts) |

## docker-compose.yml Example

For a persistent per-user setup, create a `docker-compose.yml`:

```yaml
services:
  digimate:
    image: NEXUS_REGISTRY/digimate:latest
    environment:
      DIGIMATE_BACKEND: openai
      DIGIMATE_MODEL: gpt-4.1
      DIGIMATE_API_BASE: http://host.docker.internal:8080/v1
      # DIGIMATE_API_KEY: your-key-here  # if required
    volumes:
      - ./workspace:/workspace
      - digimate-data:/root/.digimate
    # Interactive mode: uncomment below, then `docker compose run digimate`
    # stdin_open: true
    # tty: true
    # entrypoint: ["digimate", "-i"]

volumes:
  digimate-data:
```

Usage:

```bash
# Non-interactive task
docker compose run --rm digimate "refactor the auth module"

# Interactive mode
docker compose run --rm digimate -i

# JSON output (for scripts)
docker compose run --rm digimate --json "count lines of code"
```

## Custom LLM Backend

Digimate supports pluggable LLM backends via the `LLMClient` abstract class. To use your own backend:

1. Create a Python file with your `LLMClient` subclass (e.g. `my_llm.py`)
2. Mount it into the container and install it:

```yaml
services:
  digimate:
    image: NEXUS_REGISTRY/digimate:latest
    volumes:
      - ./my_llm.py:/app/my_llm.py
    environment:
      DIGIMATE_BACKEND: openai  # or configure via your module
```

If your backend exposes an OpenAI-compatible HTTP API, simply set `DIGIMATE_BACKEND=openai` and `DIGIMATE_API_BASE` to point at it — no custom code needed.

## Skills

Digimate discovers skill files (`.md`) from these directories inside the container:

| Path | Source |
|------|--------|
| `/workspace/.digimate/skills/*.md` | Project-specific skills |
| `/workspace/.github/skills/*.md` | GitHub-style skills |
| `/root/.digimate/skills/*.md` | Personal/global skills |

To add team skills, mount a directory:

```bash
docker run --rm \
  -v ./team-skills:/workspace/.digimate/skills \
  -v "$(pwd)":/workspace \
  NEXUS_REGISTRY/digimate:latest \
  "review this PR"
```

## MCP Server Configuration

To use MCP (Model Context Protocol) tool servers:

1. Create an `mcp.json` config file
2. Mount it and set `DIGIMATE_MCP_CONFIG`:

```bash
docker run --rm \
  -e DIGIMATE_MCP_CONFIG=/workspace/mcp.json \
  -v ./mcp.json:/workspace/mcp.json \
  -v "$(pwd)":/workspace \
  NEXUS_REGISTRY/digimate:latest \
  -i
```

## Usage Examples

### Non-interactive task

```bash
docker run --rm \
  -e DIGIMATE_BACKEND=openai \
  -e DIGIMATE_API_BASE=http://host.docker.internal:8080/v1 \
  -v "$(pwd)":/workspace \
  NEXUS_REGISTRY/digimate:latest \
  "find and fix all TODO comments in src/"
```

### Interactive chat

```bash
docker run --rm -it \
  -e DIGIMATE_BACKEND=openai \
  -e DIGIMATE_API_BASE=http://host.docker.internal:8080/v1 \
  -v "$(pwd)":/workspace \
  -v digimate-data:/root/.digimate \
  NEXUS_REGISTRY/digimate:latest \
  -i
```

### JSON output (CI/CD)

```bash
result=$(docker run --rm \
  -e DIGIMATE_BACKEND=openai \
  -e DIGIMATE_API_BASE=http://host.docker.internal:8080/v1 \
  -v "$(pwd)":/workspace \
  NEXUS_REGISTRY/digimate:latest \
  --json "count lines of Python code")

echo "$result" | jq .summary
```

## Troubleshooting

### LLM backend not reachable

- **Symptom**: `⚠ LLM backend not reachable`
- **Cause**: Container can't reach the API URL
- **Fix**:
  - For a service on the host machine, use `http://host.docker.internal:<port>/v1` as `DIGIMATE_API_BASE`
  - For a service on the corporate network, ensure Docker's DNS can resolve the hostname (try `docker run --rm alpine ping <hostname>`)
  - Check `DIGIMATE_API_KEY` if the backend requires authentication

### Permission denied on workspace

- **Symptom**: `Error: Permission denied: /workspace/...`
- **Fix**: Ensure the mounted directory is readable/writable. On Linux, you may need `--user $(id -u):$(id -g)`.

### Agent stuck or slow

- **Symptom**: No output for a long time
- **Fix**:
  - Increase timeout: `-e DIGIMATE_REQUEST_TIMEOUT=300`
  - Reduce iterations: `-e DIGIMATE_MAX_ITERATIONS=10`
  - Check LLM backend status independently

### Memory not persisting

- **Symptom**: Agent doesn't remember context from previous runs
- **Fix**: Mount a persistent volume for `/root/.digimate`:
  ```bash
  docker run --rm -v digimate-data:/root/.digimate ...
  ```
