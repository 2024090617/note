"""
GitHub API client — async HTTP + local git CLI.

All operations are read-only.
"""

import asyncio
import base64
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from github_mcp.config import get_config

logger = logging.getLogger(__name__)


class GitHubClient:
    """Async GitHub REST API client + local git operations."""

    def __init__(self) -> None:
        cfg = get_config()
        headers: Dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if cfg.token:
            headers["Authorization"] = f"Bearer {cfg.token}"
        self._http = httpx.AsyncClient(
            base_url=cfg.api_url,
            headers=headers,
            timeout=cfg.timeout,
            follow_redirects=True,
        )
        self._clone_dir = cfg.clone_dir
        self._max_download = cfg.max_download_size

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def _repo_dir(self, owner: str, repo: str) -> Path:
        return self._clone_dir / owner / repo

    async def _run_git(self, *args: str, cwd: Optional[Path] = None) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"git {' '.join(args)} failed ({proc.returncode}): "
                f"{stderr.decode().strip()}"
            )
        return stdout.decode().strip()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_repositories(
        self,
        query: str,
        sort: str = "best-match",
        order: str = "desc",
        per_page: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "q": query,
            "per_page": per_page,
            "page": page,
        }
        if sort != "best-match":
            params["sort"] = sort
            params["order"] = order
        return await self._get("/search/repositories", params=params)

    async def search_code(
        self,
        query: str,
        per_page: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        return await self._get(
            "/search/code",
            params={"q": query, "per_page": per_page, "page": page},
        )

    async def search_issues(
        self,
        query: str,
        sort: str = "best-match",
        order: str = "desc",
        per_page: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "q": query,
            "per_page": per_page,
            "page": page,
        }
        if sort != "best-match":
            params["sort"] = sort
            params["order"] = order
        return await self._get("/search/issues", params=params)

    # ------------------------------------------------------------------
    # Repository info
    # ------------------------------------------------------------------

    async def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        return await self._get(f"/repos/{owner}/{repo}")

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: Optional[str] = None
    ) -> Dict[str, Any]:
        params = {}
        if ref:
            params["ref"] = ref
        data = await self._get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

        # Decode base64 content for files (not directories)
        if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
            try:
                data["decoded_content"] = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except Exception:
                data["decoded_content"] = "(binary content — use download_file to save)"
        return data

    async def list_directory(
        self, owner: str, repo: str, path: str = "", ref: Optional[str] = None
    ) -> Any:
        params = {}
        if ref:
            params["ref"] = ref
        return await self._get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

    async def list_branches(
        self, owner: str, repo: str, per_page: int = 30, page: int = 1
    ) -> List[Dict[str, Any]]:
        return await self._get(
            f"/repos/{owner}/{repo}/branches",
            params={"per_page": per_page, "page": page},
        )

    async def list_tags(
        self, owner: str, repo: str, per_page: int = 30, page: int = 1
    ) -> List[Dict[str, Any]]:
        return await self._get(
            f"/repos/{owner}/{repo}/tags",
            params={"per_page": per_page, "page": page},
        )

    async def list_commits(
        self,
        owner: str,
        repo: str,
        sha: Optional[str] = None,
        path: Optional[str] = None,
        per_page: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"per_page": per_page, "page": page}
        if sha:
            params["sha"] = sha
        if path:
            params["path"] = path
        return await self._get(f"/repos/{owner}/{repo}/commits", params=params)

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 20,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        return await self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": per_page, "page": page},
        )

    async def get_pull_request(
        self, owner: str, repo: str, number: int, include_diff: bool = False
    ) -> Dict[str, Any]:
        pr = await self._get(f"/repos/{owner}/{repo}/pulls/{number}")
        if include_diff:
            resp = await self._http.get(
                f"/repos/{owner}/{repo}/pulls/{number}",
                headers={"Accept": "application/vnd.github.v3.diff"},
            )
            resp.raise_for_status()
            pr["diff"] = resp.text
        return pr

    # ------------------------------------------------------------------
    # Download (large files / LFS-aware)
    # ------------------------------------------------------------------

    async def download_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Download a file via the raw content URL (supports large / LFS files)."""
        cfg = get_config()
        dest_dir = Path(output_dir) if output_dir else cfg.clone_dir / owner / repo / "_downloads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = Path(path).name
        dest_path = dest_dir / filename

        # Build raw URL
        params = {}
        if ref:
            params["ref"] = ref
        meta = await self._get(f"/repos/{owner}/{repo}/contents/{path}", params=params)

        download_url = meta.get("download_url")
        if not download_url:
            raise ValueError(f"No download URL for {path} — may be a directory or submodule")

        # Stream download
        async with self._http.stream("GET", download_url) as resp:
            resp.raise_for_status()
            total = 0
            with open(dest_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 64):
                    total += len(chunk)
                    if total > self._max_download:
                        raise RuntimeError(
                            f"File exceeds max download size "
                            f"({self._max_download / 1024 / 1024:.0f} MB)"
                        )
                    f.write(chunk)

        return {
            "path": str(dest_path),
            "size_bytes": total,
            "size_human": _human_size(total),
            "sha": meta.get("sha", ""),
        }

    # ------------------------------------------------------------------
    # Local git operations (read-only)
    # ------------------------------------------------------------------

    async def clone_repository(
        self,
        owner: str,
        repo: str,
        shallow: bool = True,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        dest = self._repo_dir(owner, repo)
        if dest.exists():
            return {
                "status": "already_exists",
                "path": str(dest),
                "message": "Repository already cloned. Use pull_repository to update.",
            }
        dest.parent.mkdir(parents=True, exist_ok=True)

        cfg = get_config()
        # Build HTTPS clone URL, embed token for private repos
        if cfg.token:
            clone_url = f"https://x-access-token:{cfg.token}@github.com/{owner}/{repo}.git"
        else:
            clone_url = f"https://github.com/{owner}/{repo}.git"

        args = ["clone"]
        if shallow:
            args += ["--depth", "1"]
        if branch:
            args += ["--branch", branch]
        args += [clone_url, str(dest)]

        await self._run_git(*args)
        return {
            "status": "cloned",
            "path": str(dest),
            "shallow": shallow,
            "branch": branch or "(default)",
        }

    async def pull_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        dest = self._repo_dir(owner, repo)
        if not dest.exists():
            raise FileNotFoundError(
                f"Repository not cloned at {dest}. Clone it first with clone_repository."
            )
        output = await self._run_git("pull", "--ff-only", cwd=dest)
        return {"status": "pulled", "path": str(dest), "output": output}

    async def checkout_branch(
        self, owner: str, repo: str, branch: str
    ) -> Dict[str, Any]:
        dest = self._repo_dir(owner, repo)
        if not dest.exists():
            raise FileNotFoundError(
                f"Repository not cloned at {dest}. Clone it first with clone_repository."
            )
        # Fetch all remote branches if shallow clone
        try:
            await self._run_git("fetch", "--all", cwd=dest)
        except RuntimeError:
            pass  # ignore if fetch fails (e.g. no remote)
        await self._run_git("checkout", branch, cwd=dest)
        return {"status": "checked_out", "branch": branch, "path": str(dest)}


# ------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------

def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"
