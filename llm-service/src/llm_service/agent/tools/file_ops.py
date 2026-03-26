"""File operation tools."""

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .types import ToolResult


class FileOpsMixin:
    """File operation tools."""

    def read_file(self, path: str, start_line: int = 1, end_line: Optional[int] = None) -> ToolResult:
        """
        Read contents of a file.

        Args:
            path: File path (relative to workdir or absolute)
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive, None for all)

        Returns:
            ToolResult with file contents
        """
        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(False, "", f"File not found: {path}")

            if not file_path.is_file():
                return ToolResult(False, "", f"Not a file: {path}")

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            start_idx = max(0, start_line - 1)
            end_idx = end_line if end_line else len(lines)
            selected_lines = lines[start_idx:end_idx]

            content = "".join(selected_lines)
            return ToolResult(
                True,
                content,
                data={
                    "path": str(file_path),
                    "total_lines": len(lines),
                    "lines_read": len(selected_lines),
                    "start_line": start_line,
                    "end_line": end_idx,
                },
            )

        except Exception as e:
            return ToolResult(False, "", str(e))

    def write_file(self, path: str, content: str, create_dirs: bool = True) -> ToolResult:
        """
        Write content to a file.

        Args:
            path: File path
            content: Content to write
            create_dirs: Create parent directories if needed

        Returns:
            ToolResult indicating success
        """
        try:
            file_path = self._resolve_path(path)

            if create_dirs:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                True,
                f"Wrote {len(content)} bytes to {path}",
                data={"path": str(file_path), "bytes": len(content)},
            )

        except Exception as e:
            return ToolResult(False, "", str(e))

    def create_file(self, path: str, content: str = "") -> ToolResult:
        """Create a new file."""
        file_path = self._resolve_path(path)

        if file_path.exists():
            return ToolResult(False, "", f"File already exists: {path}")

        return self.write_file(path, content)

    def append_file(self, path: str, content: str) -> ToolResult:
        """Append content to a file."""
        try:
            file_path = self._resolve_path(path)

            with open(file_path, "a", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                True,
                f"Appended {len(content)} bytes to {path}",
                data={"path": str(file_path), "bytes": len(content)},
            )

        except Exception as e:
            return ToolResult(False, "", str(e))

    def delete_file(self, path: str, confirmed: bool = False) -> ToolResult:
        """
        Delete a file. Requires confirmation.

        Args:
            path: File path
            confirmed: Whether deletion is confirmed
        """
        if not confirmed and self._confirm_destructive:
            self._pending_confirmation = {
                "action": "delete_file",
                "path": path,
            }
            return ToolResult(
                False,
                f"Confirm deletion of {path}? Use /confirm to proceed.",
                data={"needs_confirmation": True},
            )

        try:
            file_path = self._resolve_path(path)

            if not file_path.exists():
                return ToolResult(False, "", f"File not found: {path}")

            file_path.unlink()
            return ToolResult(True, f"Deleted {path}")

        except Exception as e:
            return ToolResult(False, "", str(e))

    def list_directory(self, path: str = ".") -> ToolResult:
        """
        List contents of a directory.

        Args:
            path: Directory path

        Returns:
            ToolResult with directory listing
        """
        try:
            dir_path = self._resolve_path(path)

            if not dir_path.exists():
                return ToolResult(False, "", f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolResult(False, "", f"Not a directory: {path}")

            entries = []
            for entry in sorted(dir_path.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")

            return ToolResult(
                True,
                "\n".join(entries),
                data={"path": str(dir_path), "count": len(entries)},
            )

        except Exception as e:
            return ToolResult(False, "", str(e))

    # ------------------------------------------------------------------
    # Remote content download
    # ------------------------------------------------------------------

    def fetch_to_file(self, url: str, save_to: Optional[str] = None) -> ToolResult:
        """
        Download a remote URL and save its content to a local file.

        For HTML pages the tags are stripped to produce readable plain text.
        The caller can then use read_file with start_line/end_line to read
        sections incrementally without flooding the context window.

        Args:
            url: HTTP or HTTPS URL to download.
            save_to: Optional absolute path for the output file.
                     If omitted, the file is saved under
                     ``<workdir>/.digimate/cache/web/<host>/<hash>.txt``.

        Returns:
            ToolResult with saved_to path, total_lines, total_chars.
        """
        if not url or not url.strip():
            return ToolResult(False, "", "url is required")

        parsed_url = urlparse(url.strip())
        if parsed_url.scheme not in ("http", "https"):
            return ToolResult(False, "", f"Unsupported scheme: {parsed_url.scheme}. Only http/https allowed.")

        try:
            import httpx
        except ImportError:
            return ToolResult(False, "", "httpx is not installed. Run: pip install httpx")

        try:
            with httpx.Client(follow_redirects=True, timeout=30) as client:
                resp = client.get(url.strip())
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            return ToolResult(False, "", f"HTTP {e.response.status_code} from {url}")
        except Exception as e:
            return ToolResult(False, "", f"Download failed: {e}")

        content_type = resp.headers.get("content-type", "")
        raw_text = resp.text

        # Strip HTML tags to produce plain text
        if "html" in content_type.lower():
            raw_text = _strip_html(raw_text)

        # Resolve output path
        if save_to:
            file_path = Path(save_to)
        else:
            host = parsed_url.hostname or "unknown"
            # Sanitise: keep only alphanum, dash, dot
            host = re.sub(r"[^a-zA-Z0-9.\-]", "_", host)
            path_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
            file_path = self._resolve_path(
                str(Path(".digimate") / "cache" / "web" / host / f"{path_hash}.txt")
            )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(raw_text, encoding="utf-8")

        total_lines = raw_text.count("\n") + 1
        return ToolResult(
            True,
            (
                f"Saved {len(raw_text)} chars ({total_lines} lines) to {file_path}\n"
                "Use read_file with start_line/end_line to read sections."
            ),
            data={
                "saved_to": str(file_path),
                "total_lines": total_lines,
                "total_chars": len(raw_text),
                "content_type": content_type,
                "url": url.strip(),
            },
        )


# ── HTML stripping helper ────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML→text converter using stdlib only."""

    _SKIP_TAGS = frozenset({"script", "style", "head"})

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._pieces.append(data)

    def get_text(self) -> str:
        return "".join(self._pieces).strip()


def _strip_html(html: str) -> str:
    """Convert HTML to plain text, removing tags and scripts."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html)
    return extractor.get_text()
