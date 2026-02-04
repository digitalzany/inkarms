"""
HTTP request tool for making web API calls.

Supports GET, POST, PUT, DELETE methods with authentication, headers, and body.
"""

import asyncio
import json as json_lib
from typing import Any, Literal

import httpx

from inkarms.tools.base import Tool, ToolExecutionError
from inkarms.tools.models import ToolParameter, ToolResult


class HttpRequestTool(Tool):
    """Make HTTP requests to web APIs."""

    def __init__(self):
        """Initialize HTTP request tool."""
        super().__init__()

    @property
    def name(self) -> str:
        """Tool name."""
        return "http_request"

    @property
    def description(self) -> str:
        """Tool description."""
        return (
            "Make HTTP requests to web APIs. Supports GET, POST, PUT, DELETE methods "
            "with authentication, custom headers, query parameters, and request body. "
            "Parses JSON responses automatically."
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        """Tool parameters."""
        return [
            ToolParameter(
                name="url",
                type="string",
                description="The URL to request (must start with http:// or https://)",
                required=True,
            ),
            ToolParameter(
                name="method",
                type="string",
                description="HTTP method to use",
                required=False,
                default="GET",
                enum=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
            ),
            ToolParameter(
                name="headers",
                type="object",
                description="HTTP headers as key-value pairs (e.g., {'Content-Type': 'application/json'})",
                required=False,
            ),
            ToolParameter(
                name="params",
                type="object",
                description="Query parameters as key-value pairs",
                required=False,
            ),
            ToolParameter(
                name="body",
                type="string",
                description="Request body (for POST, PUT, PATCH methods). Will be sent as-is.",
                required=False,
            ),
            ToolParameter(
                name="json",
                type="object",
                description="JSON request body (alternative to 'body'). Will be serialized to JSON automatically.",
                required=False,
            ),
            ToolParameter(
                name="auth_type",
                type="string",
                description="Authentication type",
                required=False,
                enum=["none", "bearer", "basic"],
                default="none",
            ),
            ToolParameter(
                name="auth_token",
                type="string",
                description="Authentication token (for bearer auth) or password (for basic auth)",
                required=False,
            ),
            ToolParameter(
                name="auth_username",
                type="string",
                description="Username for basic authentication",
                required=False,
            ),
            ToolParameter(
                name="timeout",
                type="number",
                description="Request timeout in seconds (default: 30, max: 120)",
                required=False,
                default=30,
            ),
            ToolParameter(
                name="follow_redirects",
                type="boolean",
                description="Whether to follow HTTP redirects",
                required=False,
                default=True,
            ),
        ]

    @property
    def is_dangerous(self) -> bool:
        """HTTP requests are dangerous (can make external requests)."""
        return True

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute HTTP request."""
        self.validate_input(**kwargs)

        url: str = kwargs["url"]
        method: str = kwargs.get("method", "GET").upper()
        headers: dict[str, str] | None = kwargs.get("headers")
        params: dict[str, Any] | None = kwargs.get("params")
        body: str | None = kwargs.get("body")
        json_body: dict[str, Any] | None = kwargs.get("json")
        auth_type: str = kwargs.get("auth_type", "none")
        auth_token: str | None = kwargs.get("auth_token")
        auth_username: str | None = kwargs.get("auth_username")
        timeout: float = min(float(kwargs.get("timeout", 30)), 120.0)
        follow_redirects: bool = kwargs.get("follow_redirects", True)
        tool_call_id: str = kwargs.get("tool_call_id", "unknown")

        # Validate URL
        if not url.startswith(("http://", "https://")):
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error="URL must start with http:// or https://",
                is_error=True,
            )

        # Validate body vs json (can't use both)
        if body is not None and json_body is not None:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error="Cannot specify both 'body' and 'json' parameters",
                is_error=True,
            )

        # Build headers
        request_headers = headers.copy() if headers else {}

        # Add authentication
        if auth_type == "bearer":
            if not auth_token:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error="Bearer authentication requires 'auth_token'",
                    is_error=True,
                )
            request_headers["Authorization"] = f"Bearer {auth_token}"
        elif auth_type == "basic":
            if not auth_username or not auth_token:
                return ToolResult(
                    tool_call_id=tool_call_id,
                    output="",
                    error="Basic authentication requires 'auth_username' and 'auth_token'",
                    is_error=True,
                )
            # httpx will handle basic auth encoding

        # Prepare request kwargs
        request_kwargs: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": request_headers,
            "params": params,
            "timeout": timeout,
            "follow_redirects": follow_redirects,
        }

        # Add authentication for basic auth
        if auth_type == "basic":
            request_kwargs["auth"] = (auth_username, auth_token)

        # Add body/json
        if json_body is not None:
            request_kwargs["json"] = json_body
        elif body is not None:
            request_kwargs["content"] = body

        try:
            # Make request
            async with httpx.AsyncClient() as client:
                response = await client.request(**request_kwargs)

            # Parse response
            output_lines = [
                f"HTTP {response.status_code} {response.reason_phrase}",
                f"URL: {response.url}",
                "",
                "Headers:",
            ]

            # Show important response headers
            for key in ["content-type", "content-length", "date", "server"]:
                if key in response.headers:
                    output_lines.append(f"  {key}: {response.headers[key]}")

            output_lines.append("")

            # Parse response body
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    json_data = response.json()
                    output_lines.append("Body (JSON):")
                    output_lines.append(json_lib.dumps(json_data, indent=2))
                except Exception:
                    # Fallback to text if JSON parsing fails
                    output_lines.append("Body (text):")
                    output_lines.append(response.text[:1000])  # Limit output
                    if len(response.text) > 1000:
                        output_lines.append(f"\n... ({len(response.text)} bytes total)")
            else:
                output_lines.append("Body (text):")
                text = response.text[:1000]  # Limit output
                output_lines.append(text)
                if len(response.text) > 1000:
                    output_lines.append(f"\n... ({len(response.text)} bytes total)")

            # Determine if error based on status code
            is_error = response.status_code >= 400

            return ToolResult(
                tool_call_id=tool_call_id,
                output="\n".join(output_lines),
                error=None,
                exit_code=response.status_code,
                is_error=is_error,
            )

        except httpx.TimeoutException as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Request timed out after {timeout}s: {str(e)}",
                exit_code=-1,
                is_error=True,
            )
        except httpx.RequestError as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Request failed: {str(e)}",
                exit_code=-1,
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                output="",
                error=f"Unexpected error: {str(e)}",
                exit_code=-1,
                is_error=True,
            )
