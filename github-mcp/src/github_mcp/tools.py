"""
MCP tool definitions for GitHub operations.

All tools are read-only: search, browse, clone, pull, checkout, download.
"""

import json
import logging
from typing import Any, Dict, List

from mcp.types import TextContent, Tool

from github_mcp.client import GitHubClient
from github_mcp.config import get_config

logger = logging.getLogger(__name__)

# =====================================================================
# Tool Definitions
# =====================================================================

TOOLS: List[Tool] = [
    # ----- Search -----
    Tool(
        name="search_repositories",
        description=(
            "Search GitHub repositories. Uses the GitHub search syntax "
            "(e.g. 'language:python stars:>1000 topic:mcp'). "
            "Returns repo name, description, stars, language, and URL."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "GitHub search query (see https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)",
                },
                "sort": {
                    "type": "string",
                    "enum": ["best-match", "stars", "forks", "updated", "help-wanted-issues"],
                    "description": "Sort field. Default: best-match",
                    "default": "best-match",
                },
                "order": {
                    "type": "string",
                    "enum": ["desc", "asc"],
                    "default": "desc",
                },
                "per_page": {"type": "integer", "default": 20, "description": "Results per page (max 100)"},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="search_code",
        description=(
            "Search code across GitHub repositories. "
            "Query can include qualifiers like 'repo:owner/name', 'language:python', 'path:src/'. "
            "Returns file path, repo, and matched text fragments."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Code search query",
                },
                "per_page": {"type": "integer", "default": 20},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="search_issues",
        description=(
            "Search issues and pull requests across GitHub. "
            "Qualifiers: 'repo:owner/name', 'is:issue', 'is:pr', 'state:open', 'label:bug', etc."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Issue/PR search query"},
                "sort": {
                    "type": "string",
                    "enum": ["best-match", "comments", "reactions", "created", "updated"],
                    "default": "best-match",
                },
                "order": {"type": "string", "enum": ["desc", "asc"], "default": "desc"},
                "per_page": {"type": "integer", "default": 20},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["query"],
        },
    ),

    # ----- Repository Info -----
    Tool(
        name="get_repository",
        description="Get detailed information about a GitHub repository: description, stars, forks, language, license, default branch, topics.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner (user or org)"},
                "repo": {"type": "string", "description": "Repository name"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="get_file_content",
        description=(
            "Get the content of a file in a repository. "
            "Returns decoded text for text files. For binary files use download_file instead."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "path": {"type": "string", "description": "File path relative to repo root"},
                "ref": {"type": "string", "description": "Branch, tag, or commit SHA (optional, defaults to default branch)"},
            },
            "required": ["owner", "repo", "path"],
        },
    ),
    Tool(
        name="list_directory",
        description="List files and directories at a given path in a repository.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "path": {"type": "string", "description": "Directory path (empty string for root)", "default": ""},
                "ref": {"type": "string", "description": "Branch, tag, or commit SHA (optional)"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_branches",
        description="List branches of a repository.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "per_page": {"type": "integer", "default": 30},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_tags",
        description="List tags of a repository.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "per_page": {"type": "integer", "default": 30},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="list_commits",
        description="List commits on a branch or for a file path. Returns SHA, author, date, and message.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "sha": {"type": "string", "description": "Branch name or commit SHA to start from (optional)"},
                "path": {"type": "string", "description": "Only commits touching this path (optional)"},
                "per_page": {"type": "integer", "default": 20},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["owner", "repo"],
        },
    ),

    # ----- Pull Requests -----
    Tool(
        name="list_pull_requests",
        description="List pull requests for a repository. Filter by state (open/closed/all).",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "default": "open",
                },
                "per_page": {"type": "integer", "default": 20},
                "page": {"type": "integer", "default": 1},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="get_pull_request",
        description="Get details of a specific pull request including title, body, author, status. Optionally include the diff.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "number": {"type": "integer", "description": "PR number"},
                "include_diff": {"type": "boolean", "default": False, "description": "Include the full diff text"},
            },
            "required": ["owner", "repo", "number"],
        },
    ),

    # ----- Download -----
    Tool(
        name="download_file",
        description=(
            "Download a file from a repository to local disk. "
            "Supports large files and LFS objects. Streams the download to avoid memory issues. "
            "Returns the local path and file size."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "path": {"type": "string", "description": "File path in the repository"},
                "ref": {"type": "string", "description": "Branch, tag, or SHA (optional)"},
                "output_dir": {"type": "string", "description": "Local directory to save file (optional, defaults to clone_dir)"},
            },
            "required": ["owner", "repo", "path"],
        },
    ),

    # ----- Local Git Operations -----
    Tool(
        name="clone_repository",
        description=(
            "Clone a GitHub repository to local disk. "
            "Uses shallow clone by default for speed. "
            "Returns the local path."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "shallow": {"type": "boolean", "default": True, "description": "Shallow clone (--depth 1)"},
                "branch": {"type": "string", "description": "Branch to clone (optional)"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="pull_repository",
        description="Pull latest changes for a previously cloned repository (fast-forward only).",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["owner", "repo"],
        },
    ),
    Tool(
        name="checkout_branch",
        description="Checkout a branch in a previously cloned repository. Fetches remote branches first.",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string"},
                "repo": {"type": "string"},
                "branch": {"type": "string", "description": "Branch name to checkout"},
            },
            "required": ["owner", "repo", "branch"],
        },
    ),
]


# =====================================================================
# Tool Handlers
# =====================================================================

def _fmt(obj: Any) -> str:
    """Format an object as indented JSON."""
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


async def handle_search_repositories(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.search_repositories(
            query=args["query"],
            sort=args.get("sort", "best-match"),
            order=args.get("order", "desc"),
            per_page=args.get("per_page", 20),
            page=args.get("page", 1),
        )
        # Compact summary
        items = data.get("items", [])
        results = []
        for r in items:
            results.append({
                "full_name": r.get("full_name"),
                "description": r.get("description", ""),
                "stars": r.get("stargazers_count"),
                "language": r.get("language"),
                "url": r.get("html_url"),
                "updated_at": r.get("updated_at"),
            })
        return _fmt({"total_count": data.get("total_count"), "items": results})
    finally:
        await client.close()


async def handle_search_code(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.search_code(
            query=args["query"],
            per_page=args.get("per_page", 20),
            page=args.get("page", 1),
        )
        items = data.get("items", [])
        results = []
        for r in items:
            results.append({
                "name": r.get("name"),
                "path": r.get("path"),
                "repository": r.get("repository", {}).get("full_name"),
                "url": r.get("html_url"),
                "score": r.get("score"),
            })
        return _fmt({"total_count": data.get("total_count"), "items": results})
    finally:
        await client.close()


async def handle_search_issues(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.search_issues(
            query=args["query"],
            sort=args.get("sort", "best-match"),
            order=args.get("order", "desc"),
            per_page=args.get("per_page", 20),
            page=args.get("page", 1),
        )
        items = data.get("items", [])
        results = []
        for r in items:
            results.append({
                "title": r.get("title"),
                "number": r.get("number"),
                "state": r.get("state"),
                "user": r.get("user", {}).get("login"),
                "labels": [l.get("name") for l in r.get("labels", [])],
                "url": r.get("html_url"),
                "created_at": r.get("created_at"),
            })
        return _fmt({"total_count": data.get("total_count"), "items": results})
    finally:
        await client.close()


async def handle_get_repository(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        r = await client.get_repository(args["owner"], args["repo"])
        return _fmt({
            "full_name": r.get("full_name"),
            "description": r.get("description"),
            "homepage": r.get("homepage"),
            "stars": r.get("stargazers_count"),
            "forks": r.get("forks_count"),
            "open_issues": r.get("open_issues_count"),
            "language": r.get("language"),
            "license": (r.get("license") or {}).get("spdx_id"),
            "default_branch": r.get("default_branch"),
            "topics": r.get("topics", []),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "url": r.get("html_url"),
            "clone_url": r.get("clone_url"),
            "size_kb": r.get("size"),
        })
    finally:
        await client.close()


async def handle_get_file_content(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.get_file_content(
            args["owner"], args["repo"], args["path"], ref=args.get("ref"),
        )
        if isinstance(data, dict) and "decoded_content" in data:
            return data["decoded_content"]
        return _fmt(data)
    finally:
        await client.close()


async def handle_list_directory(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.list_directory(
            args["owner"], args["repo"], path=args.get("path", ""), ref=args.get("ref"),
        )
        if isinstance(data, list):
            items = []
            for entry in data:
                items.append({
                    "name": entry.get("name"),
                    "type": entry.get("type"),
                    "size": entry.get("size"),
                    "path": entry.get("path"),
                })
            return _fmt(items)
        return _fmt(data)
    finally:
        await client.close()


async def handle_list_branches(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.list_branches(
            args["owner"], args["repo"],
            per_page=args.get("per_page", 30),
            page=args.get("page", 1),
        )
        branches = [{"name": b["name"], "sha": b["commit"]["sha"]} for b in data]
        return _fmt(branches)
    finally:
        await client.close()


async def handle_list_tags(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.list_tags(
            args["owner"], args["repo"],
            per_page=args.get("per_page", 30),
            page=args.get("page", 1),
        )
        tags = [{"name": t["name"], "sha": t["commit"]["sha"]} for t in data]
        return _fmt(tags)
    finally:
        await client.close()


async def handle_list_commits(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.list_commits(
            args["owner"], args["repo"],
            sha=args.get("sha"),
            path=args.get("path"),
            per_page=args.get("per_page", 20),
            page=args.get("page", 1),
        )
        commits = []
        for c in data:
            commits.append({
                "sha": c["sha"][:12],
                "message": c["commit"]["message"].split("\n")[0],
                "author": c["commit"]["author"]["name"],
                "date": c["commit"]["author"]["date"],
            })
        return _fmt(commits)
    finally:
        await client.close()


async def handle_list_pull_requests(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        data = await client.list_pull_requests(
            args["owner"], args["repo"],
            state=args.get("state", "open"),
            per_page=args.get("per_page", 20),
            page=args.get("page", 1),
        )
        prs = []
        for pr in data:
            prs.append({
                "number": pr["number"],
                "title": pr["title"],
                "state": pr["state"],
                "user": pr["user"]["login"],
                "created_at": pr["created_at"],
                "url": pr["html_url"],
            })
        return _fmt(prs)
    finally:
        await client.close()


async def handle_get_pull_request(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        pr = await client.get_pull_request(
            args["owner"], args["repo"], args["number"],
            include_diff=args.get("include_diff", False),
        )
        result: Dict[str, Any] = {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "user": pr["user"]["login"],
            "body": pr.get("body", ""),
            "head": pr["head"]["label"],
            "base": pr["base"]["label"],
            "mergeable": pr.get("mergeable"),
            "additions": pr.get("additions"),
            "deletions": pr.get("deletions"),
            "changed_files": pr.get("changed_files"),
            "created_at": pr["created_at"],
            "url": pr["html_url"],
        }
        if "diff" in pr:
            result["diff"] = pr["diff"]
        return _fmt(result)
    finally:
        await client.close()


async def handle_download_file(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        result = await client.download_file(
            args["owner"], args["repo"], args["path"],
            ref=args.get("ref"),
            output_dir=args.get("output_dir"),
        )
        return _fmt(result)
    finally:
        await client.close()


async def handle_clone_repository(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        result = await client.clone_repository(
            args["owner"], args["repo"],
            shallow=args.get("shallow", True),
            branch=args.get("branch"),
        )
        return _fmt(result)
    finally:
        await client.close()


async def handle_pull_repository(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        result = await client.pull_repository(args["owner"], args["repo"])
        return _fmt(result)
    finally:
        await client.close()


async def handle_checkout_branch(args: Dict[str, Any]) -> str:
    client = GitHubClient()
    try:
        result = await client.checkout_branch(
            args["owner"], args["repo"], args["branch"],
        )
        return _fmt(result)
    finally:
        await client.close()


# =====================================================================
# Registry & Dispatcher
# =====================================================================

TOOL_HANDLERS = {
    "search_repositories": handle_search_repositories,
    "search_code": handle_search_code,
    "search_issues": handle_search_issues,
    "get_repository": handle_get_repository,
    "get_file_content": handle_get_file_content,
    "list_directory": handle_list_directory,
    "list_branches": handle_list_branches,
    "list_tags": handle_list_tags,
    "list_commits": handle_list_commits,
    "list_pull_requests": handle_list_pull_requests,
    "get_pull_request": handle_get_pull_request,
    "download_file": handle_download_file,
    "clone_repository": handle_clone_repository,
    "pull_repository": handle_pull_repository,
    "checkout_branch": handle_checkout_branch,
}


async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Dispatch a tool call by name."""
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        result = await handler(arguments)
        return [TextContent(type="text", text=result)]
    except Exception as e:
        logger.error(f"Tool {name} failed: {e}", exc_info=True)
        return [TextContent(type="text", text=f"Error: {str(e)}")]
