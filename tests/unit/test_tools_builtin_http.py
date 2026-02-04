"""Tests for HTTP request tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from inkarms.tools.builtin.http import HttpRequestTool
from inkarms.tools.models import ToolResult


@pytest.fixture
def http_tool():
    """Create HTTP tool instance."""
    return HttpRequestTool()


def test_http_tool_initialization(http_tool):
    """Test HTTP tool is initialized correctly."""
    assert http_tool.name == "http_request"
    assert http_tool.is_dangerous is True
    assert len(http_tool.parameters) == 11  # url, method, headers, params, body, json, auth_type, auth_token, auth_username, timeout, follow_redirects

    # Check required parameters
    param_dict = {p.name: p for p in http_tool.parameters}
    assert param_dict["url"].required is True
    assert param_dict["method"].required is False
    assert param_dict["method"].default == "GET"


def test_http_tool_schema(http_tool):
    """Test JSON schema generation."""
    schema = http_tool.get_input_schema()
    assert schema["type"] == "object"
    assert "url" in schema["properties"]
    assert "method" in schema["properties"]
    assert "url" in schema["required"]

    # Check method enum
    assert "enum" in schema["properties"]["method"]
    assert "GET" in schema["properties"]["method"]["enum"]
    assert "POST" in schema["properties"]["method"]["enum"]


def test_validate_invalid_url():
    """Test validation rejects invalid URLs."""
    tool = HttpRequestTool()
    with pytest.raises(ValueError, match="Unknown parameters"):
        tool.validate_input(invalid_param="value")


@pytest.mark.asyncio
async def test_http_get_request_success(http_tool):
    """Test successful GET request."""
    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.url = "https://api.example.com/data"
    mock_response.headers = {
        "content-type": "application/json",
        "content-length": "42"
    }
    mock_response.json.return_value = {"key": "value"}
    mock_response.text = '{"key": "value"}'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test1",
            url="https://api.example.com/data",
            method="GET"
        )

    assert result.tool_call_id == "test1"
    assert result.is_error is False
    assert result.exit_code == 200
    assert "HTTP 200 OK" in result.output
    assert "application/json" in result.output
    assert '"key": "value"' in result.output


@pytest.mark.asyncio
async def test_http_post_request_with_json(http_tool):
    """Test POST request with JSON body."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.reason_phrase = "Created"
    mock_response.url = "https://api.example.com/items"
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"id": 123}
    mock_response.text = '{"id": 123}'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test2",
            url="https://api.example.com/items",
            method="POST",
            json={"name": "test"}
        )

    assert result.is_error is False
    assert result.exit_code == 201
    assert "HTTP 201 Created" in result.output

    # Verify request was called with json parameter
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["json"] == {"name": "test"}


@pytest.mark.asyncio
async def test_http_request_with_bearer_auth(http_tool):
    """Test request with bearer authentication."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.url = "https://api.example.com/secure"
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.text = "Success"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test3",
            url="https://api.example.com/secure",
            auth_type="bearer",
            auth_token="secret-token-123"
        )

    assert result.is_error is False

    # Verify bearer token was added to headers
    call_kwargs = mock_client.request.call_args[1]
    assert "Authorization" in call_kwargs["headers"]
    assert call_kwargs["headers"]["Authorization"] == "Bearer secret-token-123"


@pytest.mark.asyncio
async def test_http_request_with_basic_auth(http_tool):
    """Test request with basic authentication."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.url = "https://api.example.com/secure"
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.text = "Success"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test4",
            url="https://api.example.com/secure",
            auth_type="basic",
            auth_username="user",
            auth_token="pass"
        )

    assert result.is_error is False

    # Verify basic auth was passed
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["auth"] == ("user", "pass")


@pytest.mark.asyncio
async def test_http_request_error_status(http_tool):
    """Test request with error status code."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.reason_phrase = "Not Found"
    mock_response.url = "https://api.example.com/missing"
    mock_response.headers = {"content-type": "text/plain"}
    mock_response.text = "Resource not found"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test5",
            url="https://api.example.com/missing"
        )

    assert result.is_error is True  # 404 is an error
    assert result.exit_code == 404
    assert "HTTP 404 Not Found" in result.output


@pytest.mark.asyncio
async def test_http_request_invalid_url(http_tool):
    """Test request with invalid URL scheme."""
    result = await http_tool.execute(
        tool_call_id="test6",
        url="ftp://example.com"
    )

    assert result.is_error is True
    assert "must start with http://" in result.error


@pytest.mark.asyncio
async def test_http_request_body_and_json_conflict(http_tool):
    """Test that using both body and json parameters fails."""
    result = await http_tool.execute(
        tool_call_id="test7",
        url="https://api.example.com/data",
        body="raw text",
        json={"key": "value"}
    )

    assert result.is_error is True
    assert "Cannot specify both 'body' and 'json'" in result.error


@pytest.mark.asyncio
async def test_http_request_bearer_auth_missing_token(http_tool):
    """Test bearer auth without token fails."""
    result = await http_tool.execute(
        tool_call_id="test8",
        url="https://api.example.com/secure",
        auth_type="bearer"
    )

    assert result.is_error is True
    assert "requires 'auth_token'" in result.error


@pytest.mark.asyncio
async def test_http_request_timeout(http_tool):
    """Test request timeout handling."""
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test9",
            url="https://api.example.com/slow",
            timeout=5
        )

    assert result.is_error is True
    assert "timed out" in result.error.lower()
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_http_request_network_error(http_tool):
    """Test request network error handling."""
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.RequestError("Network error"))
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test10",
            url="https://api.example.com/data"
        )

    assert result.is_error is True
    assert "Request failed" in result.error
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_http_request_with_custom_headers(http_tool):
    """Test request with custom headers."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.url = "https://api.example.com/data"
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {}
    mock_response.text = "{}"

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test11",
            url="https://api.example.com/data",
            headers={"X-Custom": "value", "Accept": "application/json"}
        )

    assert result.is_error is False

    # Verify headers were passed
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["headers"]["X-Custom"] == "value"
    assert call_kwargs["headers"]["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_http_request_with_query_params(http_tool):
    """Test request with query parameters."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.reason_phrase = "OK"
    mock_response.url = "https://api.example.com/search?q=test&limit=10"
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json.return_value = {"results": []}
    mock_response.text = '{"results": []}'

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_class.return_value.__aenter__.return_value = mock_client

        result = await http_tool.execute(
            tool_call_id="test12",
            url="https://api.example.com/search",
            params={"q": "test", "limit": 10}
        )

    assert result.is_error is False

    # Verify params were passed
    call_kwargs = mock_client.request.call_args[1]
    assert call_kwargs["params"] == {"q": "test", "limit": 10}
