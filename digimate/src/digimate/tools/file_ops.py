"""File operation tools with Layer 2 read-guard."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from digimate.core.types import ToolResult


def make_file_tools(resolve_path, *, read_file_auto_limit: int = 500):
    """Return a dict of {name: (fn, mutating)} file-op tool functions.

    ``resolve_path`` is a callable that converts relative paths to absolute.
    """

    # ── read_file (with Layer 2 auto-cap) ────────────────────────────

    def read_file(
        path: str, start_line: int = 1, end_line: Optional[int] = None,
    ) -> ToolResult:
        try:
            fp = resolve_path(path)
            if not fp.exists():
                return ToolResult(False, "", f"File not found: {path}")
            if not fp.is_file():
                return ToolResult(False, "", f"Not a file: {path}")

            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total = len(lines)
            start_idx = max(0, start_line - 1)

            # Layer 2 guard: auto-cap unbounded reads on large files
            if end_line is None and total > read_file_auto_limit:
                show = min(200, total)
                selected = lines[start_idx : start_idx + show]
                content = "".join(selected)
                header = (
                    f"[Showing lines {start_line}-{start_line + show - 1} of {total}. "
                    f"Specify start_line/end_line for more.]\n"
                )
                return ToolResult(True, header + content, data={
                    "path": str(fp), "total_lines": total,
                    "lines_read": show, "auto_capped": True,
                })

            end_idx = end_line if end_line else total
            selected = lines[start_idx:end_idx]
            return ToolResult(True, "".join(selected), data={
                "path": str(fp), "total_lines": total,
                "lines_read": len(selected),
                "start_line": start_line, "end_line": end_idx,
            })
        except Exception as e:
            return ToolResult(False, "", str(e))

    # ── write_file ───────────────────────────────────────────────────

    def write_file(path: str, content: str) -> ToolResult:
        try:
            fp = resolve_path(path)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")
            return ToolResult(True, f"Wrote {len(content)} bytes to {path}",
                              data={"path": str(fp), "bytes": len(content)})
        except Exception as e:
            return ToolResult(False, "", str(e))

    # ── create_file ──────────────────────────────────────────────────

    def create_file(path: str, content: str = "") -> ToolResult:
        fp = resolve_path(path)
        if fp.exists():
            return ToolResult(False, "", f"File already exists: {path}")
        return write_file(path, content)

    # ── patch_file (search-and-replace) ──────────────────────────────

    def patch_file(path: str, old_string: str, new_string: str) -> ToolResult:
        try:
            fp = resolve_path(path)
            if not fp.is_file():
                return ToolResult(False, "", f"File not found: {path}")
            text = fp.read_text(encoding="utf-8")
            count = text.count(old_string)
            if count == 0:
                return ToolResult(False, "", "old_string not found in file")
            if count > 1:
                return ToolResult(False, "", f"old_string found {count} times — must be unique")
            new_text = text.replace(old_string, new_string, 1)
            fp.write_text(new_text, encoding="utf-8")
            return ToolResult(True, f"Patched {path} (1 replacement)")
        except Exception as e:
            return ToolResult(False, "", str(e))

    # ── delete_file ──────────────────────────────────────────────────

    def delete_file(path: str) -> ToolResult:
        try:
            fp = resolve_path(path)
            if not fp.exists():
                return ToolResult(False, "", f"File not found: {path}")
            fp.unlink()
            return ToolResult(True, f"Deleted {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    # ── list_directory ───────────────────────────────────────────────

    def list_directory(path: str = ".") -> ToolResult:
        try:
            dp = resolve_path(path)
            if not dp.is_dir():
                return ToolResult(False, "", f"Not a directory: {path}")
            entries = []
            for e in sorted(dp.iterdir()):
                entries.append(f"{e.name}/" if e.is_dir() else e.name)
            return ToolResult(True, "\n".join(entries),
                              data={"path": str(dp), "count": len(entries)})
        except Exception as e:
            return ToolResult(False, "", str(e))

    # ── append_file ──────────────────────────────────────────────────

    def append_file(path: str, content: str) -> ToolResult:
        try:
            fp = resolve_path(path)
            with open(fp, "a", encoding="utf-8") as f:
                f.write(content)
            return ToolResult(True, f"Appended {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))

    return {
        "read_file":      (read_file, False),
        "write_file":     (write_file, True),
        "create_file":    (create_file, True),
        "patch_file":     (patch_file, True),
        "delete_file":    (delete_file, True),
        "list_directory": (list_directory, False),
        "append_file":    (append_file, True),
    }


# ── Web fetch (Layer 2: preview + path) ─────────────────────────────

def make_web_tools(resolve_path, *, web_preview_lines: int = 200):
    """Return web-related tool functions."""

    def fetch_url(url: str, save_to: Optional[str] = None, verify_ssl: bool = True) -> ToolResult:
        if not url or not url.strip():
            return ToolResult(False, "", "url is required")

        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return ToolResult(False, "", f"Unsupported scheme: {parsed.scheme}")

        try:
            import httpx
        except ImportError:
            return ToolResult(False, "", "httpx is not installed")

        # Use HTTP/2 only if h2 is available
        try:
            import h2  # noqa: F401
            use_http2 = True
        except ImportError:
            use_http2 = False

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        # Try with SSL verification first, fall back to unverified on SSL errors
        last_error = None
        for attempt_verify in ([True, False] if verify_ssl else [False]):
            try:
                with httpx.Client(
                    follow_redirects=True,
                    timeout=httpx.Timeout(30.0, connect=15.0),
                    verify=attempt_verify,
                    http2=use_http2,
                ) as client:
                    resp = client.get(url.strip(), headers=headers)
                    resp.raise_for_status()
                break
            except (httpx.ConnectError, httpx.RemoteProtocolError) as e:
                err_str = str(e).lower()
                if "ssl" in err_str or "tls" in err_str or "certificate" in err_str:
                    last_error = e
                    if attempt_verify:
                        continue  # retry without SSL verify
                return ToolResult(False, "", f"Connection failed: {e}")
            except httpx.TimeoutException as e:
                last_error = e
                if attempt_verify:
                    continue  # retry without SSL verify on timeout
                return ToolResult(False, "", f"Request timed out: {e}")
            except Exception as e:
                return ToolResult(False, "", f"Download failed: {e}")
        else:
            return ToolResult(False, "", f"Download failed after SSL fallback: {last_error}")

        content_type = resp.headers.get("content-type", "")
        raw = resp.text
        if "html" in content_type.lower():
            raw = _strip_html(raw)

        # Save full content to disk
        if save_to:
            fp = Path(save_to)
        else:
            host = re.sub(r"[^a-zA-Z0-9.\-]", "_", parsed.hostname or "unknown")
            h = hashlib.sha256(url.encode()).hexdigest()[:12]
            fp = resolve_path(f".digimate/cache/web/{host}/{h}.txt")

        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(raw, encoding="utf-8")

        total_lines = raw.count("\n") + 1
        total_chars = len(raw)

        # Layer 2: return preview only
        lines = raw.splitlines(keepends=True)
        preview_count = min(web_preview_lines, len(lines))
        preview = "".join(lines[:preview_count])

        header = (
            f"[Fetched {total_chars:,} chars ({total_lines} lines) → {fp}]\n"
            f"[Showing first {preview_count} lines. Use read_file for more.]\n\n"
        )

        return ToolResult(True, header + preview, data={
            "saved_to": str(fp), "total_lines": total_lines,
            "total_chars": total_chars, "url": url.strip(),
        })

    return {"fetch_url": (fetch_url, False)}


# ── HTML stripping ───────────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    _SKIP = frozenset({"script", "style", "head"})

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._pieces.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0:
            self._pieces.append(data)

    def get_text(self) -> str:
        return "".join(self._pieces).strip()


def _strip_html(html: str) -> str:
    ext = _HTMLTextExtractor()
    ext.feed(html)
    return ext.get_text()
