"""Search and discovery tools."""

import re

from .types import ToolResult


class SearchOpsMixin:
    """Search operations."""

    def search_files(self, pattern: str, path: str = ".") -> ToolResult:
        """
        Search for files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py")
            path: Base path to search from

        Returns:
            ToolResult with matching file paths
        """
        try:
            base_path = self._resolve_path(path)
            matches = list(base_path.glob(pattern))

            matches = matches[:100]
            relative_paths = [str(m.relative_to(base_path)) for m in matches]

            return ToolResult(
                True,
                "\n".join(relative_paths),
                data={"pattern": pattern, "count": len(relative_paths)},
            )

        except Exception as e:
            return ToolResult(False, "", str(e))

    def grep_search(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = "*",
        ignore_case: bool = True,
    ) -> ToolResult:
        """
        Search for text pattern in files.

        Args:
            pattern: Regex pattern to search
            path: Base path
            file_pattern: Glob pattern for files to search
            ignore_case: Case insensitive search

        Returns:
            ToolResult with matching lines
        """
        try:
            base_path = self._resolve_path(path)
            flags = re.IGNORECASE if ignore_case else 0
            regex = re.compile(pattern, flags)

            results = []
            files_searched = 0

            for file_path in base_path.rglob(file_pattern):
                if not file_path.is_file():
                    continue
                if any(part.startswith(".") for part in file_path.parts):
                    continue
                if "node_modules" in file_path.parts or "__pycache__" in file_path.parts:
                    continue

                files_searched += 1
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                rel_path = file_path.relative_to(base_path)
                                results.append(f"{rel_path}:{line_num}: {line.rstrip()}")

                                if len(results) >= 50:
                                    break
                except Exception:
                    pass

                if len(results) >= 50:
                    break

            output = "\n".join(results) if results else "No matches found"
            return ToolResult(
                True,
                output,
                data={
                    "pattern": pattern,
                    "matches": len(results),
                    "files_searched": files_searched,
                },
            )

        except Exception as e:
            return ToolResult(False, "", str(e))
