"""Tests for hub OpenAI-compatible proxy endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _make_app():
    from inkarms.hub.api import openai as openai_module
    app = fastapi.FastAPI()
    app.include_router(openai_module.router)
    return app


def _make_config(openai_proxy: bool = True, default_model: str = "claude-sonnet-4-6"):
    cfg = MagicMock()
    cfg.hub.openai_proxy = openai_proxy
    cfg.providers.default = default_model
    return cfg


def _make_completion_response(content="Hello!", model="claude-sonnet-4-6", cost=0.001):
    resp = MagicMock()
    resp.content = content
    resp.model = model
    resp.cost = cost
    resp.finish_reason = "stop"
    resp.usage = MagicMock()
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 20
    resp.fallback_from = None
    return resp


class TestOpenAIProxyDisabled:
    def test_returns_404_when_disabled(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        cfg = _make_config(openai_proxy=False)

        with patch("inkarms.hub.api.openai.get_config", return_value=cfg):
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 404


class TestOpenAIProxyNonStreaming:
    def test_non_streaming_response(self) -> None:
        app = _make_app()
        client = TestClient(app)
        cfg = _make_config()
        completion = _make_completion_response()

        mock_manager = MagicMock()
        mock_manager.complete = AsyncMock(return_value=completion)

        with (
            patch("inkarms.hub.api.openai.get_config", return_value=cfg),
            patch("inkarms.hub.api.openai.get_provider_manager", return_value=mock_manager),
            patch("inkarms.providers.CompletionResponse", MagicMock),
        ):
            resp = client.post(
                "/v1/chat/completions",
                json={
                    "model": "claude-sonnet-4-6",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "chat.completion"
        assert data["choices"][0]["message"]["content"] == "Hello!"
        assert data["choices"][0]["finish_reason"] == "stop"
        assert data["usage"]["total_tokens"] == 30

    def test_missing_messages_returns_400(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        cfg = _make_config()

        with patch("inkarms.hub.api.openai.get_config", return_value=cfg):
            resp = client.post("/v1/chat/completions", json={"model": "gpt-4"})

        assert resp.status_code == 400

    def test_provider_unavailable_returns_503(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        cfg = _make_config()

        with (
            patch("inkarms.hub.api.openai.get_config", return_value=cfg),
            patch(
                "inkarms.hub.api.openai.get_provider_manager",
                side_effect=RuntimeError("no provider"),
            ),
        ):
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert resp.status_code == 503


class TestOpenAIProxyCronAPI:
    """Basic cron API endpoint tests."""

    def test_list_empty(self) -> None:
        fastapi_mod = pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from unittest.mock import AsyncMock, patch
        from inkarms.hub.api import cron as cron_module

        app = fastapi_mod.FastAPI()
        app.include_router(cron_module.router)
        client = TestClient(app)

        with patch(
            "inkarms.hub.api.cron.hub_db.execute_fetchall",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/api/cron")

        assert resp.status_code == 200
        assert resp.json()["jobs"] == []
        assert resp.json()["total"] == 0

    def test_create_duplicate_returns_409(self) -> None:
        fastapi_mod = pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from unittest.mock import AsyncMock, MagicMock, patch
        from inkarms.hub.api import cron as cron_module

        app = fastapi_mod.FastAPI()
        app.include_router(cron_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        existing = MagicMock()
        existing.__getitem__ = lambda s, k: "existing-id"

        with (
            patch(
                "inkarms.hub.api.cron.hub_db.execute_fetchone",
                new_callable=AsyncMock,
                return_value=existing,
            ),
        ):
            resp = client.post(
                "/api/cron",
                json={
                    "id": "my-job",
                    "schedule": "every 1m",
                    "type": "bash",
                    "command": "echo hi",
                },
            )

        assert resp.status_code == 409

    def test_delete_not_found_returns_404(self) -> None:
        fastapi_mod = pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from unittest.mock import AsyncMock, patch
        from inkarms.hub.api import cron as cron_module

        app = fastapi_mod.FastAPI()
        app.include_router(cron_module.router)
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "inkarms.hub.api.cron.hub_db.execute_fetchone",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.delete("/api/cron/ghost-job")

        assert resp.status_code == 404
