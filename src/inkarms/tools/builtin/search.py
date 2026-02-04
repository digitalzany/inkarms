"""File search and content search tools."""

import logging
import re
from pathlib import Path
from typing import List, Optional

from inkarms.tools.base import Tool, ToolExecutionError
from inkarms.tools.models import ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class SearchFilesTool(Tool):
    """Search for files and content within files.

    Safe read-only operation for finding files by name or searching content.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "search_files"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Search for files by name pattern or search content within files. "
            "Can search by filename pattern (glob) or by text content (grep). "
            "Use this to: find files matching a pattern, locate files containing "
            "specific text, search code for functions/classes, find configuration "
            "files, search logs for errors, etc."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="path",
                type="string",
                description=(
                    "Directory path to search in. "
                    "Defaults to current directory. "
                    "Example: '.' or '/home/user/projects'"
                ),
                required=False,
                default=".",
            ),
            ToolParameter(
                name="pattern",
                type="string",
                description=(
                    "Pattern to search for. "
                    "Can be a filename glob pattern (e.g., '*.py', 'test_*.txt') "
                    "or text content to search for if content_search is true. "
                    "Example: '*.py' or 'def main'"
                ),
                required=True,
            ),
            ToolParameter(
                name="content_search",
                type="boolean",
                description=(
                    "If true, search file contents for pattern (grep-like). "
                    "If false, search filenames for pattern (glob-like). "
                    "Default: false."
                ),
                required=False,
                default=False,
            ),
            ToolParameter(
                name="case_sensitive",
                type="boolean",
                description=(
                    "Case-sensitive search. Only applies to content search. "
                    "Default: false (case-insensitive)."
                ),
                required=False,
                default=False,
            ),
            ToolParameter(
                name="file_pattern",
                type="string",
                description=(
                    "Optional filename pattern to filter which files to search "
                    "when doing content search. "
                    "Example: '*.py' to search only Python files. "
                    "Only used when content_search is true."
                ),
                required=False,
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description=(
                    "Maximum number of results to return. " "Default: 100."
                ),
                required=False,
                default=100,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """Search operations are safe."""
        return False

    async def execute(self, **kwargs) -> ToolResult:
        """Search for files or content.

        Args:
            path: Directory to search in
            pattern: Search pattern (glob or text)
            content_search: Search content vs filenames
            case_sensitive: Case-sensitive content search
            file_pattern: Filter files when content searching
            max_results: Max results to return

        Returns:
            ToolResult with search results
        """
        self.validate_input(**kwargs)

        path = kwargs.get("path", ".")
        pattern = kwargs["pattern"]
        content_search = kwargs.get("content_search", False)
        case_sensitive = kwargs.get("case_sensitive", False)
        file_pattern = kwargs.get("file_pattern")
        max_results = kwargs.get("max_results", 100)
        tool_call_id = kwargs.get("tool_call_id", "unknown")

        logger.info(f"Searching files: {path} for '{pattern}'")

        try:
            search_path = Path(path).expanduser().resolve()

            # Check if directory exists
            if not search_path.exists():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Directory not found: {path}",
                    is_error=True,
                )

            if not search_path.is_dir():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Not a directory: {path}",
                    is_error=True,
                )

            # Perform search
            if content_search:
                results = await self._search_content(
                    search_path,
                    pattern,
                    case_sensitive,
                    file_pattern,
                    max_results,
                )
            else:
                results = await self._search_filenames(
                    search_path, pattern, max_results
                )

            # Format output
            if not results:
                output = f"No results found for: {pattern}"
            else:
                output_lines = [
                    f"Search: {pattern}",
                    f"Results: {len(results)} (max: {max_results})",
                    "",
                ]
                output_lines.extend(results)
                output = "\n".join(output_lines)

            return ToolResult(
                tool_call_id=tool_call_id,
                output=output,
                is_error=False,
            )

        except PermissionError:
            error_msg = f"Permission denied: {path}"
            logger.warning(f"Search permission denied: {path}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )

        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            logger.error(f"Search error: {path}: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )

    async def _search_filenames(
        self, base_path: Path, pattern: str, max_results: int
    ) -> List[str]:
        """Search for files by name pattern.

        Args:
            base_path: Base directory to search
            pattern: Glob pattern
            max_results: Max results

        Returns:
            List of matching file paths
        """
        results = []

        try:
            # Use rglob for recursive glob matching
            for match in base_path.rglob(pattern):
                if len(results) >= max_results:
                    break

                # Get relative path
                rel_path = match.relative_to(base_path)

                # Get type
                if match.is_dir():
                    type_str = "DIR "
                else:
                    type_str = "FILE"

                results.append(f"{type_str}  {rel_path}")

        except Exception as e:
            logger.warning(f"Error during filename search: {e}")

        return results

    async def _search_content(
        self,
        base_path: Path,
        pattern: str,
        case_sensitive: bool,
        file_pattern: Optional[str],
        max_results: int,
    ) -> List[str]:
        """Search for text content within files.

        Args:
            base_path: Base directory to search
            pattern: Text pattern to find
            case_sensitive: Case-sensitive search
            file_pattern: Optional filename filter
            max_results: Max results

        Returns:
            List of matching lines with file and line number
        """
        results = []

        # Compile regex pattern
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            # If pattern is not valid regex, treat as literal string
            regex = re.compile(re.escape(pattern), flags)

        # Get files to search
        if file_pattern:
            files = list(base_path.rglob(file_pattern))
        else:
            # Search all files (skip common binary/generated directories)
            files = [
                f
                for f in base_path.rglob("*")
                if f.is_file()
                and not any(
                    part.startswith(".")
                    or part in {"node_modules", "__pycache__", "venv", ".git"}
                    for part in f.parts
                )
            ]

        # Search each file
        for file_path in files:
            if len(results) >= max_results:
                break

            # Skip binary files (heuristic: check for null bytes in first 8KB)
            try:
                with open(file_path, "rb") as f:
                    sample = f.read(8192)
                    if b"\x00" in sample:
                        continue  # Binary file
            except (OSError, PermissionError):
                continue

            # Search file content
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line_num, line in enumerate(f, start=1):
                        if len(results) >= max_results:
                            break

                        if regex.search(line):
                            rel_path = file_path.relative_to(base_path)
                            # Strip whitespace and limit line length
                            line_preview = line.strip()[:100]
                            results.append(
                                f"{rel_path}:{line_num}: {line_preview}"
                            )

            except (UnicodeDecodeError, PermissionError, OSError):
                # Skip files that can't be read
                continue

        return results
