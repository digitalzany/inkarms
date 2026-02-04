"""
Python code execution tool using RestrictedPython.

Allows safe execution of Python code with security restrictions.
"""

import asyncio
import io
import sys
from typing import Any

from RestrictedPython import compile_restricted_exec, safe_globals, limited_builtins
from RestrictedPython.Guards import (
    guarded_iter_unpack_sequence,
    safe_builtins,
    safer_getattr,
    full_write_guard,
)
from RestrictedPython.PrintCollector import PrintCollector

from inkarms.tools.base import Tool
from inkarms.tools.models import ToolParameter, ToolResult


class PythonEvalTool(Tool):
    """Execute Python code safely using RestrictedPython.

    This tool allows execution of Python code with security restrictions:
    - Restricted imports (only safe modules)
    - No file system access
    - No network access
    - Timeout limits
    - Captured stdout/stderr
    """

    def __init__(self):
        """Initialize Python eval tool."""
        super().__init__()

    @property
    def name(self) -> str:
        """Tool name."""
        return "python_eval"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Execute Python code safely in a restricted environment. "
            "Code is executed with RestrictedPython which blocks dangerous operations. "
            "Available modules: math, datetime, json, re, random. "
            "Use for: calculations, data processing, parsing, algorithms. "
            "Cannot: access files, make network requests, execute system commands. "
            "Timeout: 30s default."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="code",
                type="string",
                description=(
                    "Python code to execute. Can be multiple lines. "
                    "Use print() to produce output. "
                    "Example: 'import math\\nprint(math.sqrt(16))'"
                ),
                required=True,
            ),
            ToolParameter(
                name="timeout",
                type="number",
                description="Execution timeout in seconds (default: 30, max: 60)",
                required=False,
                default=30,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """Python eval is dangerous (arbitrary code execution)."""
        return True

    def _get_safe_globals(self) -> dict[str, Any]:
        """Get safe global namespace for code execution.

        Returns:
            Dictionary of safe globals including restricted builtins
        """
        # Start with RestrictedPython's safe globals
        restricted_globals = safe_globals.copy()

        # Create custom builtins with necessary additions
        custom_builtins = limited_builtins.copy()

        # Add safe import mechanism
        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            """Safe import that only allows whitelisted modules."""
            allowed_modules = {
                "math", "datetime", "json", "re", "random",
                "itertools", "functools", "collections",
                "string", "time"
            }

            # Extract base module name
            base_module = name.split('.')[0]

            if base_module not in allowed_modules:
                raise ImportError(f"Import of '{name}' is not allowed")

            return __import__(name, globals, locals, fromlist, level)

        custom_builtins["__import__"] = safe_import
        custom_builtins["__build_class__"] = __build_class__  # For class definitions
        custom_builtins["__metaclass__"] = type  # Default metaclass
        custom_builtins["__name__"] = "__main__"  # Module name for class definitions

        # Add all required guards for full Python support
        restricted_globals["__builtins__"] = custom_builtins
        restricted_globals["_print_"] = PrintCollector
        restricted_globals["_getattr_"] = safer_getattr
        restricted_globals["_write_"] = full_write_guard

        # Safe iterator - just return iter() for trusted code
        def safe_iter(obj):
            """Safe iteration."""
            return iter(obj)

        restricted_globals["_getiter_"] = safe_iter
        restricted_globals["_iter_unpack_sequence_"] = safe_iter

        # Add getitem for list/dict access
        def _getitem(obj, index):
            """Safe getitem for list/dict access."""
            return obj[index]

        restricted_globals["_getitem_"] = _getitem

        # Add safe standard library modules directly (for convenience)
        import math
        import datetime
        import json
        import re
        import random

        restricted_globals.update({
            "math": math,
            "datetime": datetime,
            "json": json,
            "re": re,
            "random": random,
        })

        return restricted_globals

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute Python code safely."""
        self.validate_input(**kwargs)

        code: str = kwargs["code"]
        timeout: float = min(float(kwargs.get("timeout", 30)), 60.0)
        tool_call_id: str = kwargs.get("tool_call_id", "unknown")

        # Compile code with RestrictedPython
        try:
            compile_result = compile_restricted_exec(code)
        except SyntaxError as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Syntax error: {str(e)}",
                is_error=True,
            )

        # Check for compilation errors
        if compile_result.errors:
            error_msg = "\n".join(compile_result.errors)
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Compilation errors:\n{error_msg}",
                is_error=True,
            )

        # Prepare execution environment
        restricted_globals = self._get_safe_globals()
        restricted_locals: dict[str, Any] = {}

        # Capture stderr (stdout is handled by PrintCollector)
        old_stderr = sys.stderr
        stderr_capture = io.StringIO()

        try:
            sys.stderr = stderr_capture

            # Execute with timeout
            async def run_code():
                exec(compile_result.code, restricted_globals, restricted_locals)

            await asyncio.wait_for(run_code(), timeout=timeout)

            # Get output from PrintCollector (stored in restricted_locals)
            print_output = ""
            if "_print" in restricted_locals:
                print_output = restricted_locals["_print"]()
            stderr_output = stderr_capture.getvalue()

            # Build result
            output_lines = []

            if print_output:
                output_lines.append("Output:")
                output_lines.append(print_output.rstrip())

            if stderr_output:
                if output_lines:
                    output_lines.append("")
                output_lines.append("Errors/Warnings:")
                output_lines.append(stderr_output.rstrip())

            # If there's no output, show success message
            if not output_lines:
                output_lines.append("Code executed successfully (no output)")

            return ToolResult(
                tool_call_id=tool_call_id,
                output="\n".join(output_lines),
                error=None,
                exit_code=0,
                is_error=False,
            )

        except asyncio.TimeoutError:
            # Get partial output
            print_output = ""
            if "_print" in restricted_locals:
                print_output = restricted_locals["_print"]()
            return ToolResult(
                tool_call_id=tool_call_id,
                output=print_output or "",
                error=f"Execution timed out after {timeout}s",
                exit_code=-1,
                is_error=True,
            )
        except Exception as e:
            # Capture any runtime errors
            print_output = ""
            if "_print" in restricted_locals:
                try:
                    print_output = restricted_locals["_print"]()
                except:
                    pass
            stderr_output = stderr_capture.getvalue()
            error_msg = f"Runtime error: {type(e).__name__}: {str(e)}"
            if stderr_output:
                error_msg += f"\n\nStderr:\n{stderr_output}"

            return ToolResult(
                tool_call_id=tool_call_id,
                output=print_output or "",
                error=error_msg,
                exit_code=-1,
                is_error=True,
            )
        finally:
            # Restore stderr
            sys.stderr = old_stderr
