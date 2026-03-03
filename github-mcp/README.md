# GitHub MCP Server

Read-only MCP server for GitHub — search, browse, clone, pull, checkout, and large-file download.

## Features

| Category | Tools |
|----------|-------|
| **Search** | `search_repositories`, `search_code`, `search_issues` |
| **Browse** | `get_repository`, `get_file_content`, `list_directory`, `list_branches`, `list_tags`, `list_commits` |
| **Pull Requests** | `list_pull_requests`, `get_pull_request` |
| **Git Operations** | `clone_repository`, `pull_repository`, `checkout_branch` |
| **Download** | `download_file` (LFS-aware, large binary files) |

All operations are **read-only** — no push, no write, no delete.

## Configuration

Set environment variables or create a `.env` file:

```env
# Required — GitHub personal access token
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Optional
GITHUB_API_URL=https://api.github.com    # For GitHub Enterprise
GITHUB_CLONE_DIR=~/github-repos           # Where to clone repos
```

## Usage

### Standalone
```bash
pip install -e .
github-mcp
```

### With the agent (mcp.json)
```json
{
  "mcpServers": {
    "github": {
      "command": "github-mcp",
      "env": {
        "GITHUB_TOKEN": "ghp_xxxxxxxxxxxx"
      }
    }
  }
}
```

### Example tool calls

Search repos:
```json
{"tool": "search_repositories", "arguments": {"query": "language:python stars:>1000 topic:mcp"}}
```

Read a file:
```json
{"tool": "get_file_content", "arguments": {"owner": "anthropics", "repo": "claude-code", "path": "README.md"}}
```

Clone and checkout:
```json
{"tool": "clone_repository", "arguments": {"owner": "anthropics", "repo": "claude-code", "shallow": true}}
{"tool": "checkout_branch", "arguments": {"owner": "anthropics", "repo": "claude-code", "branch": "develop"}}
```

Download a large file:
```json
{"tool": "download_file", "arguments": {"owner": "user", "repo": "models", "path": "weights/model.bin", "output_dir": "/tmp"}}
```
