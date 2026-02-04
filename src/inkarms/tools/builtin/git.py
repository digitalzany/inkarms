"""
Git operations tool for version control.

Provides safe git operations through GitPython library.
"""

from typing import Any, Optional

from git import Repo, GitCommandError, InvalidGitRepositoryError
from pathlib import Path

from inkarms.tools.base import Tool
from inkarms.tools.models import ToolParameter, ToolResult


class GitOperationsTool(Tool):
    """Execute common git operations safely.

    This tool provides version control operations including status, log, diff,
    add, commit, branch, and checkout. All operations are performed through
    GitPython with safety checks.
    """

    def __init__(self):
        """Initialize git operations tool."""
        super().__init__()

    @property
    def name(self) -> str:
        """Tool name."""
        return "git_operation"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Perform git version control operations. Supports: status, log, diff, "
            "add, commit, branch, checkout. Use this for: checking repository status, "
            "viewing commit history, seeing file changes, staging files, creating commits, "
            "managing branches. All operations work on the specified repository path."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="operation",
                type="string",
                description="Git operation to perform",
                required=True,
                enum=["status", "log", "diff", "add", "commit", "branch", "checkout"],
            ),
            ToolParameter(
                name="repo_path",
                type="string",
                description="Path to git repository (default: current directory)",
                required=False,
                default=".",
            ),
            ToolParameter(
                name="file_path",
                type="string",
                description="File path for add/diff operations",
                required=False,
            ),
            ToolParameter(
                name="message",
                type="string",
                description="Commit message (required for commit operation)",
                required=False,
            ),
            ToolParameter(
                name="branch_name",
                type="string",
                description="Branch name for branch/checkout operations",
                required=False,
            ),
            ToolParameter(
                name="create_branch",
                type="boolean",
                description="Create new branch when checking out (default: false)",
                required=False,
                default=False,
            ),
            ToolParameter(
                name="max_count",
                type="number",
                description="Maximum number of log entries to show (default: 10)",
                required=False,
                default=10,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """Git operations are dangerous (can modify repository state)."""
        return True

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute git operation."""
        self.validate_input(**kwargs)

        operation: str = kwargs["operation"]
        repo_path: str = kwargs.get("repo_path", ".")
        file_path: Optional[str] = kwargs.get("file_path")
        message: Optional[str] = kwargs.get("message")
        branch_name: Optional[str] = kwargs.get("branch_name")
        create_branch: bool = kwargs.get("create_branch", False)
        max_count: int = int(kwargs.get("max_count", 10))
        tool_call_id: str = kwargs.get("tool_call_id", "unknown")

        try:
            # Open repository
            repo = Repo(Path(repo_path).expanduser().resolve())

            if operation == "status":
                return await self._git_status(repo, tool_call_id)
            elif operation == "log":
                return await self._git_log(repo, max_count, tool_call_id)
            elif operation == "diff":
                return await self._git_diff(repo, file_path, tool_call_id)
            elif operation == "add":
                return await self._git_add(repo, file_path, tool_call_id)
            elif operation == "commit":
                return await self._git_commit(repo, message, tool_call_id)
            elif operation == "branch":
                return await self._git_branch(repo, branch_name, tool_call_id)
            elif operation == "checkout":
                return await self._git_checkout(repo, branch_name, create_branch, tool_call_id)
            else:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error=f"Unknown operation: {operation}",
                    is_error=True,
                )

        except InvalidGitRepositoryError:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Not a git repository: {repo_path}",
                is_error=True,
            )
        except GitCommandError as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Git command failed: {str(e)}",
                exit_code=e.status,
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Error: {str(e)}",
                is_error=True,
            )

    async def _git_status(self, repo: Repo, tool_call_id: str) -> ToolResult:
        """Get repository status."""
        output_lines = [
            f"Branch: {repo.active_branch.name}",
            "",
        ]

        # Check if anything is staged
        if repo.index.diff("HEAD"):
            output_lines.append("Changes to be committed:")
            for diff in repo.index.diff("HEAD"):
                change_type = "modified" if diff.change_type == "M" else diff.change_type
                output_lines.append(f"  {change_type}: {diff.a_path}")
            output_lines.append("")

        # Check for unstaged changes
        if repo.index.diff(None):
            output_lines.append("Changes not staged for commit:")
            for diff in repo.index.diff(None):
                change_type = "modified" if diff.change_type == "M" else diff.change_type
                output_lines.append(f"  {change_type}: {diff.a_path}")
            output_lines.append("")

        # Check for untracked files
        if repo.untracked_files:
            output_lines.append("Untracked files:")
            for file in repo.untracked_files:
                output_lines.append(f"  {file}")
            output_lines.append("")

        # Clean status
        if len(output_lines) == 2:  # Only branch line
            output_lines.append("Working tree clean")

        return ToolResult(
            tool_call_id=tool_call_id,
            output="\n".join(output_lines),
            exit_code=0,
            is_error=False,
        )

    async def _git_log(self, repo: Repo, max_count: int, tool_call_id: str) -> ToolResult:
        """Get commit log."""
        output_lines = []

        for commit in repo.iter_commits(max_count=max_count):
            output_lines.append(f"commit {commit.hexsha}")
            output_lines.append(f"Author: {commit.author.name} <{commit.author.email}>")
            output_lines.append(f"Date:   {commit.committed_datetime}")
            output_lines.append("")
            output_lines.append(f"    {commit.message}")
            output_lines.append("")

        if not output_lines:
            output_lines.append("No commits yet")

        return ToolResult(
            tool_call_id=tool_call_id,
            output="\n".join(output_lines),
            exit_code=0,
            is_error=False,
        )

    async def _git_diff(self, repo: Repo, file_path: Optional[str], tool_call_id: str) -> ToolResult:
        """Get diff for changes."""
        if file_path:
            # Diff for specific file
            diff = repo.git.diff(file_path)
        else:
            # Diff for all changes
            diff = repo.git.diff()

        if not diff:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="No changes",
                exit_code=0,
                is_error=False,
            )

        return ToolResult(
            tool_call_id=tool_call_id,
            output=diff,
            exit_code=0,
            is_error=False,
        )

    async def _git_add(self, repo: Repo, file_path: Optional[str], tool_call_id: str) -> ToolResult:
        """Add files to staging area."""
        if not file_path:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error="file_path parameter required for add operation",
                is_error=True,
            )

        repo.index.add([file_path])
        return ToolResult(
            tool_call_id=tool_call_id,
            output=f"Added: {file_path}",
            exit_code=0,
            is_error=False,
        )

    async def _git_commit(self, repo: Repo, message: Optional[str], tool_call_id: str) -> ToolResult:
        """Create a commit."""
        if not message:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error="message parameter required for commit operation",
                is_error=True,
            )

        # Check if there are staged changes
        if not repo.index.diff("HEAD"):
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error="No changes staged for commit",
                is_error=True,
            )

        commit = repo.index.commit(message)
        return ToolResult(
            tool_call_id=tool_call_id,
            output=f"Created commit: {commit.hexsha[:8]} - {message}",
            exit_code=0,
            is_error=False,
        )

    async def _git_branch(self, repo: Repo, branch_name: Optional[str], tool_call_id: str) -> ToolResult:
        """List branches or create new branch."""
        if not branch_name:
            # List all branches
            output_lines = ["Branches:"]
            for branch in repo.branches:
                marker = "*" if branch == repo.active_branch else " "
                output_lines.append(f"{marker} {branch.name}")

            return ToolResult(
                tool_call_id=tool_call_id,
                output="\n".join(output_lines),
                exit_code=0,
                is_error=False,
            )
        else:
            # Create new branch
            repo.create_head(branch_name)
            return ToolResult(
                tool_call_id=tool_call_id,
                output=f"Created branch: {branch_name}",
                exit_code=0,
                is_error=False,
            )

    async def _git_checkout(
        self, repo: Repo, branch_name: Optional[str], create_branch: bool, tool_call_id: str
    ) -> ToolResult:
        """Checkout a branch."""
        if not branch_name:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error="branch_name parameter required for checkout operation",
                is_error=True,
            )

        if create_branch:
            # Create and checkout new branch
            new_branch = repo.create_head(branch_name)
            new_branch.checkout()
            return ToolResult(
                tool_call_id=tool_call_id,
                output=f"Created and checked out branch: {branch_name}",
                exit_code=0,
                is_error=False,
            )
        else:
            # Checkout existing branch
            repo.heads[branch_name].checkout()
            return ToolResult(
                tool_call_id=tool_call_id,
                output=f"Checked out branch: {branch_name}",
                exit_code=0,
                is_error=False,
            )
