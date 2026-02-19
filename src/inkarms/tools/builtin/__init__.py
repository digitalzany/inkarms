"""Built-in tools for InkArms agent.

This module provides standard tools that enable the AI agent to:
- Execute bash commands
- Read and write files
- List directory contents
- Search for files and content
- Make HTTP requests to web APIs
- Execute Python code safely (requires RestrictedPython)
- Perform Git operations (requires GitPython)
"""

from inkarms.tools.builtin.bash import BashTool
from inkarms.tools.builtin.file import ListFilesTool, ReadFileTool, WriteFileTool
from inkarms.tools.builtin.http import HttpRequestTool
from inkarms.tools.builtin.registry_utils import register_builtin_tools
from inkarms.tools.builtin.search import SearchFilesTool
from inkarms.tools.builtin.web_search import BraveSearchTool

# Optional tools (require extra dependencies)
try:
    from inkarms.tools.builtin.python import PythonEvalTool
    _PYTHON_EVAL_AVAILABLE = True
except ImportError:
    _PYTHON_EVAL_AVAILABLE = False
    PythonEvalTool = None  # type: ignore

try:
    from inkarms.tools.builtin.git import GitOperationsTool
    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False
    GitOperationsTool = None  # type: ignore

__all__ = [
    "BashTool",
    "BraveSearchTool",
    "GitOperationsTool",
    "HttpRequestTool",
    "ListFilesTool",
    "PythonEvalTool",
    "ReadFileTool",
    "SearchFilesTool",
    "WriteFileTool",
    "register_builtin_tools",
]
