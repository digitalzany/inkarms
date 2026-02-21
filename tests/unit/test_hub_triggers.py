"""Tests for hub trigger webhook ingress."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _make_app():
    from inkarms.hub.api import triggers as triggers_module
    app = fastapi.FastAPI()
    app.include_router(triggers_module.router)
    return app


def _make_config(triggers=None, max_body_bytes=1048576, webhook_tool_approval_mode="auto"):
    cfg = MagicMock()
    cfg.hub.triggers = triggers or []
    cfg.hub.trigger_max_body_bytes = max_body_bytes
    cfg.hub.webhook_tool_approval_mode = webhook_tool_approval_mode
    return cfg


def _make_trigger(name="test-trigger", prompt_template="Hello {body.name}", shared_secret=None,
                  secret_header="X-Hub-Signature-256", session_id="default"):
    t = MagicMock()
    t.name = name
    t.prompt_template = prompt_template
    t.shared_secret = shared_secret
    t.secret_header = secret_header
    t.session_id = session_id
    return t


class TestRenderTemplate:
    def test_body_placeholder(self) -> None:
        from inkarms.hub.api.triggers import render_template
        result = render_template("{body.name}", {"name": "Alice"}, {}, {})
        assert result == "Alice"

    def test_nested_body_path(self) -> None:
        from inkarms.hub.api.triggers import render_template
        result = render_template(
            "{body.repo.name}",
            {"repo": {"name": "inkarms"}},
            {},
            {},
        )
        assert result == "inkarms"

    def test_headers_placeholder(self) -> None:
        from inkarms.hub.api.triggers import render_template
        result = render_template("{headers.x-event}", {}, {"x-event": "push"}, {})
        assert result == "push"

    def test_query_placeholder(self) -> None:
        from inkarms.hub.api.triggers import render_template
        result = render_template("{query.action}", {}, {}, {"action": "deploy"})
        assert result == "deploy"

    def test_missing_key_returns_empty(self) -> None:
        from inkarms.hub.api.triggers import render_template
        result = render_template("{body.missing}", {}, {}, {})
        assert result == ""

    def test_excessive_depth_returns_empty(self) -> None:
        from inkarms.hub.api.triggers import render_template
        # More than 5 nested keys → empty
        result = render_template("{body.a.b.c.d.e.f}", {"a": {}}, {}, {})
        assert result == ""

    def test_no_format_map_injection(self) -> None:
        """Arbitrary {python_format_string} placeholders are left unchanged."""
        from inkarms.hub.api.triggers import render_template
        template = "Hello {name}"  # no root namespace prefix
        result = render_template(template, {"name": "Alice"}, {}, {})
        assert result == "Hello {name}"  # untouched — no injection


class TestVerifySignature:
    def test_valid_signature(self) -> None:
        from inkarms.hub.api.triggers import _verify_signature
        body = b'{"event": "push"}'
        secret = "my-secret"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_signature(body, secret, f"sha256={sig}")

    def test_invalid_signature(self) -> None:
        from inkarms.hub.api.triggers import _verify_signature
        assert not _verify_signature(b"body", "secret", "sha256=baddigest")

    def test_without_sha256_prefix(self) -> None:
        """Header without sha256= prefix is also accepted."""
        from inkarms.hub.api.triggers import _verify_signature
        body = b"test"
        secret = "secret"
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_signature(body, secret, sig)  # no prefix


class TestHandleTrigger:
    def test_trigger_not_found(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        cfg = _make_config(triggers=[])

        with patch("inkarms.hub.api.triggers.get_config", return_value=cfg):
            resp = client.post(
                "/triggers/nonexistent",
                json={"key": "value"},
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 404

    def test_body_too_large(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        trigger = _make_trigger(name="my-trigger")
        cfg = _make_config(triggers=[trigger], max_body_bytes=10)

        with patch("inkarms.hub.api.triggers.get_config", return_value=cfg):
            resp = client.post(
                "/triggers/my-trigger",
                content=b"x" * 20,
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 413

    def test_wrong_content_type(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        trigger = _make_trigger(name="my-trigger")
        cfg = _make_config(triggers=[trigger])

        with patch("inkarms.hub.api.triggers.get_config", return_value=cfg):
            resp = client.post(
                "/triggers/my-trigger",
                content=b"plain text",
                headers={"content-type": "text/plain"},
            )
        assert resp.status_code == 415

    def test_missing_hmac_signature(self) -> None:
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=False)
        trigger = _make_trigger(name="my-trigger", shared_secret="secret")
        cfg = _make_config(triggers=[trigger])

        with patch("inkarms.hub.api.triggers.get_config", return_value=cfg):
            resp = client.post(
                "/triggers/my-trigger",
                json={"name": "Alice"},
            )
        assert resp.status_code == 401

    def test_accepted_fires_background_task(self) -> None:
        import asyncio
        app = _make_app()
        client = TestClient(app, raise_server_exceptions=True)
        trigger = _make_trigger(
            name="my-trigger",
            prompt_template="Process {body.name}",
        )
        cfg = _make_config(triggers=[trigger])

        with (
            patch("inkarms.hub.api.triggers.get_config", return_value=cfg),
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_create_task.return_value = MagicMock()
            resp = client.post(
                "/triggers/my-trigger",
                json={"name": "Alice"},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert data["trigger"] == "my-trigger"
        mock_create_task.assert_called_once()
