"""File operation tools."""

from typing import Optional

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
