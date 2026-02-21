"""Tests for hub /health and /api/status endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Skip entire module if fastapi is not installed
fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from inkarms.hub.api import status as status_module  # noqa: E402


def _make_test_app() -> "fastapi.FastAPI":
    """Create a minimal FastAPI app with only the status router (no auth middleware)."""
    app = fastapi.FastAPI()
    app.include_router(status_module.router)
    return app


class TestHealthEndpoint:
    def test_health_returns_ok(self) -> None:
        app = _make_test_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_unauthenticated(self) -> None:
        """Health endpoint must be reachable without any auth headers."""
        app = _make_test_app()
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200


class TestStatusEndpoint:
    def test_status_returns_running(self) -> None:
        status_module.set_start_time(1_000_000.0)

        app = _make_test_app()
        client = TestClient(app)

        mock_cfg = MagicMock()
        mock_cfg.hub.host = "127.0.0.1"
        mock_cfg.hub.port = 18750
        mock_cfg.providers.default = "anthropic/claude-sonnet-4-6"
        mock_cfg.cost.budgets.daily = 5.0

        mock_tracker = MagicMock()
        mock_tracker.today_cost = 1.23
        mock_tracker.daily_limit = 5.0

        # Patch at the source location since status.py uses lazy imports
        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch("inkarms.hub.budget.get_budget_tracker", return_value=mock_tracker),
        ):
            resp = client.get("/api/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "running"
        assert data["port"] == 18750
        assert data["model"] == "anthropic/claude-sonnet-4-6"
        assert data["budget"]["today_cost"] == pytest.approx(1.23)

    def test_status_without_budget_tracker(self) -> None:
        """Status should not crash if BudgetTracker is not initialised."""
        app = _make_test_app()
        client = TestClient(app)

        mock_cfg = MagicMock()
        mock_cfg.hub.host = "127.0.0.1"
        mock_cfg.hub.port = 18750
        mock_cfg.providers.default = "test-model"

        with (
            patch("inkarms.config.loader.get_config", return_value=mock_cfg),
            patch(
                "inkarms.hub.budget.get_budget_tracker",
                side_effect=RuntimeError("not init"),
            ),
        ):
            resp = client.get("/api/status")

        assert resp.status_code == 200
        assert resp.json()["budget"] == {}
