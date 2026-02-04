"""File operation tools."""

import logging
import os
from pathlib import Path
from typing import Optional

from inkarms.tools.base import Tool, ToolExecutionError
from inkarms.tools.models import ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class ReadFileTool(Tool):
    """Read file contents.

    Safe read-only operation that reads text files and returns their content.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "read_file"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Read the contents of a text file. "
            "Returns the full file content as a string. "
            "Use this to: examine source code, read configuration files, "
            "inspect logs, analyze data files, etc. "
            "For large files, consider reading specific sections only."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="path",
                type="string",
                description=(
                    "Path to the file to read. "
                    "Can be absolute or relative to current directory. "
                    "Example: 'config.yaml' or '/home/user/notes.txt'"
                ),
                required=True,
            ),
            ToolParameter(
                name="encoding",
                type="string",
                description=(
                    "File encoding. Default: 'utf-8'. "
                    "Use 'latin-1' for non-UTF8 files."
                ),
                required=False,
                default="utf-8",
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """Read operations are safe."""
        return False

    async def execute(self, **kwargs) -> ToolResult:
        """Read file contents.

        Args:
            path: Path to file
            encoding: File encoding (default: utf-8)

        Returns:
            ToolResult with file contents
        """
        self.validate_input(**kwargs)

        path = kwargs["path"]
        encoding = kwargs.get("encoding", "utf-8")
        tool_call_id = kwargs.get("tool_call_id", "unknown")

        logger.info(f"Reading file: {path}")

        try:
            file_path = Path(path).expanduser().resolve()

            # Check if file exists
            if not file_path.exists():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"File not found: {path}",
                    is_error=True,
                )

            # Check if it's a file (not directory)
            if not file_path.is_file():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Not a file: {path}",
                    is_error=True,
                )

            # Read file
            content = file_path.read_text(encoding=encoding)

            # Add metadata
            file_size = file_path.stat().st_size
            output = f"File: {path}\nSize: {file_size} bytes\n\n{content}"

            return ToolResult(
                tool_call_id=tool_call_id,
                output=output,
                is_error=False,
            )

        except UnicodeDecodeError as e:
            error_msg = (
                f"Failed to decode file with {encoding} encoding. "
                f"Try a different encoding (e.g., 'latin-1')"
            )
            logger.warning(f"File encoding error: {path}: {e}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )

        except PermissionError:
            error_msg = f"Permission denied: {path}"
            logger.warning(f"File permission denied: {path}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )

        except Exception as e:
            error_msg = f"Failed to read file: {str(e)}"
            logger.error(f"File read error: {path}: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )


class WriteFileTool(Tool):
    """Write content to a file.

    Dangerous operation that creates or overwrites files.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "write_file"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Write content to a file, creating it if needed or overwriting if exists. "
            "Use this to: create new files, update configuration, save generated code, "
            "write logs, create documentation, etc. "
            "CAUTION: This will overwrite existing files without confirmation!"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="path",
                type="string",
                description=(
                    "Path where file should be written. "
                    "Parent directory must exist. "
                    "Example: 'output.txt' or '/tmp/results.json'"
                ),
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description=(
                    "Content to write to the file. "
                    "Can be text, code, JSON, YAML, etc."
                ),
                required=True,
            ),
            ToolParameter(
                name="encoding",
                type="string",
                description="File encoding. Default: 'utf-8'.",
                required=False,
                default="utf-8",
            ),
            ToolParameter(
                name="create_dirs",
                type="boolean",
                description=(
                    "Create parent directories if they don't exist. "
                    "Default: false."
                ),
                required=False,
                default=False,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """Write operations can modify system state."""
        return True

    async def execute(self, **kwargs) -> ToolResult:
        """Write file contents.

        Args:
            path: Path to file
            content: Content to write
            encoding: File encoding (default: utf-8)
            create_dirs: Create parent directories if needed

        Returns:
            ToolResult with success/failure message
        """
        self.validate_input(**kwargs)

        path = kwargs["path"]
        content = kwargs["content"]
        encoding = kwargs.get("encoding", "utf-8")
        create_dirs = kwargs.get("create_dirs", False)
        tool_call_id = kwargs.get("tool_call_id", "unknown")

        logger.info(f"Writing file: {path}")

        try:
            file_path = Path(path).expanduser().resolve()

            # Create parent directories if requested
            if create_dirs and not file_path.parent.exists():
                file_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if parent directory exists
            if not file_path.parent.exists():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Parent directory does not exist: {file_path.parent}",
                    is_error=True,
                )

            # Write file
            file_path.write_text(content, encoding=encoding)

            # Build success message
            file_size = file_path.stat().st_size
            existed = "Updated" if file_path.exists() else "Created"
            output = f"{existed} file: {path}\nSize: {file_size} bytes"

            return ToolResult(
                tool_call_id=tool_call_id,
                output=output,
                is_error=False,
            )

        except PermissionError:
            error_msg = f"Permission denied: {path}"
            logger.warning(f"File permission denied: {path}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )

        except Exception as e:
            error_msg = f"Failed to write file: {str(e)}"
            logger.error(f"File write error: {path}: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )


class ListFilesTool(Tool):
    """List directory contents.

    Safe read-only operation that lists files and directories.
    """

    @property
    def name(self) -> str:
        """Tool name."""
        return "list_files"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "List files and directories in a given path. "
            "Returns file names, types, sizes, and modification times. "
            "Use this to: explore directory structure, find files, "
            "check what files exist, analyze project layout, etc."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="path",
                type="string",
                description=(
                    "Directory path to list. "
                    "Defaults to current directory if not specified. "
                    "Example: '.' or '/home/user/projects'"
                ),
                required=False,
                default=".",
            ),
            ToolParameter(
                name="recursive",
                type="boolean",
                description=(
                    "List files recursively in subdirectories. "
                    "Default: false. Use carefully with large directories."
                ),
                required=False,
                default=False,
            ),
            ToolParameter(
                name="show_hidden",
                type="boolean",
                description=(
                    "Show hidden files (starting with '.'). " "Default: false."
                ),
                required=False,
                default=False,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """List operations are safe."""
        return False

    async def execute(self, **kwargs) -> ToolResult:
        """List directory contents.

        Args:
            path: Directory path (default: current directory)
            recursive: List recursively (default: false)
            show_hidden: Show hidden files (default: false)

        Returns:
            ToolResult with directory listing
        """
        self.validate_input(**kwargs)

        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)
        show_hidden = kwargs.get("show_hidden", False)
        tool_call_id = kwargs.get("tool_call_id", "unknown")

        logger.info(f"Listing directory: {path}")

        try:
            dir_path = Path(path).expanduser().resolve()

            # Check if directory exists
            if not dir_path.exists():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Directory not found: {path}",
                    is_error=True,
                )

            # Check if it's a directory
            if not dir_path.is_dir():
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Not a directory: {path}",
                    is_error=True,
                )

            # Collect entries
            entries = []

            if recursive:
                # Recursive listing
                for item in dir_path.rglob("*"):
                    if not show_hidden and item.name.startswith("."):
                        continue
                    entries.append(item)
            else:
                # Non-recursive listing
                for item in dir_path.iterdir():
                    if not show_hidden and item.name.startswith("."):
                        continue
                    entries.append(item)

            # Sort entries
            entries.sort()

            # Format output
            output_lines = [f"Directory: {path}", f"Total entries: {len(entries)}", ""]

            for item in entries:
                # Get relative path
                rel_path = item.relative_to(dir_path)

                # Get type
                if item.is_dir():
                    type_str = "DIR "
                elif item.is_symlink():
                    type_str = "LINK"
                else:
                    type_str = "FILE"

                # Get size
                try:
                    size = item.stat().st_size
                    if size < 1024:
                        size_str = f"{size}B"
                    elif size < 1024 * 1024:
                        size_str = f"{size / 1024:.1f}KB"
                    else:
                        size_str = f"{size / (1024 * 1024):.1f}MB"
                except (OSError, PermissionError):
                    size_str = "???"

                # Format line
                output_lines.append(f"{type_str}  {size_str:>10}  {rel_path}")

            output = "\n".join(output_lines)

            return ToolResult(
                tool_call_id=tool_call_id,
                output=output,
                is_error=False,
            )

        except PermissionError:
            error_msg = f"Permission denied: {path}"
            logger.warning(f"Directory permission denied: {path}")
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )

        except Exception as e:
            error_msg = f"Failed to list directory: {str(e)}"
            logger.error(f"Directory list error: {path}: {e}", exc_info=True)
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=error_msg,
                is_error=True,
            )
