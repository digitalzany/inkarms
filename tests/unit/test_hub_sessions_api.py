"""Tests for hub /api/sessions endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inkarms.hub.api import sessions as sessions_module  # noqa: E402


def _make_app() -> "fastapi.FastAPI":
    app = fastapi.FastAPI()
    app.include_router(sessions_module.router)
    return app


def _make_row(session_id: str = "test-session", platform: str = "hub") -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "session_id": session_id,
        "platform": platform,
        "platform_user_id": None,
        "channel_id": None,
        "display_name": None,
        "created_at": "2026-02-20T10:00:00",
        "last_active": "2026-02-20T10:05:00",
        "turn_count": 3,
        "total_tokens": 1500,
        "total_cost": 0.012,
        "primary_model": "claude-sonnet-4-6",
    }[k]
    return row


class TestListSessions:
    def test_list_sessions_empty(self) -> None:
        app = _make_app()
        client = TestClient(app)

        with (
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchall", new_callable=AsyncMock, return_value=[]),
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchone", new_callable=AsyncMock, return_value=MagicMock(__getitem__=lambda s, k: 0)),
        ):
            resp = client.get("/api/sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions"] == []
        assert data["total"] == 0

    def test_list_sessions_returns_rows(self) -> None:
        app = _make_app()
        client = TestClient(app)
        row = _make_row()
        count_row = MagicMock()
        count_row.__getitem__ = lambda s, k: 1

        with (
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchall", new_callable=AsyncMock, return_value=[row]),
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchone", new_callable=AsyncMock, return_value=count_row),
        ):
            resp = client.get("/api/sessions")

        assert resp.status_code == 200
        sessions = resp.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "test-session"
        assert sessions[0]["platform"] == "hub"

    def test_list_sessions_platform_filter(self) -> None:
        """platform query parameter is passed through to DB query."""
        app = _make_app()
        client = TestClient(app)
        count_row = MagicMock()
        count_row.__getitem__ = lambda s, k: 0

        captured_params = {}

        async def mock_fetchall(query, params=()):
            captured_params["params"] = params
            return []

        with (
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchall", side_effect=mock_fetchall),
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchone", new_callable=AsyncMock, return_value=count_row),
        ):
            client.get("/api/sessions?platform=telegram")

        # "telegram" should be in the query params
        assert "telegram" in captured_params.get("params", ())


class TestGetSession:
    def test_get_session_found(self) -> None:
        app = _make_app()
        client = TestClient(app)
        row = _make_row("my-session")

        with (
            patch("inkarms.hub.api.sessions.hub_db.execute_fetchone", new_callable=AsyncMock, return_value=row),
            patch("inkarms.hub.api.sessions._load_recent_turns", return_value=[]),
        ):
            resp = client.get("/api/sessions/my-session")

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "my-session"

    def test_get_session_not_found(self) -> None:
        app = _make_app()
        client = TestClient(app)

        with patch("inkarms.hub.api.sessions.hub_db.execute_fetchone", new_callable=AsyncMock, return_value=None):
            resp = client.get("/api/sessions/nonexistent")

        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete_session_ok(self) -> None:
        app = _make_app()
        client = TestClient(app)

        with (
            patch("inkarms.hub.api.sessions.hub_db.delete_session", new_callable=AsyncMock, return_value=True),
            patch("inkarms.hub.api.sessions._delete_session_files"),
        ):
            resp = client.delete("/api/sessions/my-session")

        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_session_not_found(self) -> None:
        app = _make_app()
        client = TestClient(app)

        with patch("inkarms.hub.api.sessions.hub_db.delete_session", new_callable=AsyncMock, return_value=False):
            resp = client.delete("/api/sessions/ghost")

        assert resp.status_code == 404
