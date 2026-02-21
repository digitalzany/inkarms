"""Tests for hub PID file management."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from inkarms.hub.pid import (
    HubAlreadyRunningError,
    HubPIDError,
    MAX_ACQUIRE_RETRIES,
    _is_stale,
    _read_pid,
    acquire,
    read,
)


class TestPIDHelpers:
    def test_read_pid_missing_file(self, tmp_path: Path) -> None:
        assert read(tmp_path / "hub.pid") is None

    def test_read_pid_valid(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "hub.pid"
        pid_file.write_text("12345")
        assert _read_pid(pid_file) == 12345

    def test_read_pid_invalid(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "hub.pid"
        pid_file.write_text("not-a-pid")
        assert _read_pid(pid_file) == 0

    def test_is_stale_current_process(self) -> None:
        # Current process is live — not stale
        assert _is_stale(os.getpid()) is False

    def test_is_stale_invalid_pid(self) -> None:
        # PID 0 or negative is stale by definition
        assert _is_stale(0) is True
        assert _is_stale(-1) is True

    def test_is_stale_dead_pid(self) -> None:
        # Very large PID unlikely to exist
        assert _is_stale(9_999_999) is True


class TestAcquire:
    def test_acquire_creates_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "hub.pid"
        acquire(pid_file)
        assert pid_file.exists()
        assert int(pid_file.read_text()) == os.getpid()

    def test_acquire_raises_if_live_process(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "hub.pid"
        # Write current PID as if another instance is running
        pid_file.write_text(str(os.getpid()))
        with pytest.raises(HubAlreadyRunningError) as exc_info:
            acquire(pid_file)
        assert exc_info.value.pid == os.getpid()

    def test_acquire_overwrites_stale_pid(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "hub.pid"
        # Write a guaranteed-dead PID
        pid_file.write_text("9999999")
        acquire(pid_file)
        assert int(pid_file.read_text()) == os.getpid()

    def test_acquire_creates_parent_dirs(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "subdir" / "hub.pid"
        acquire(pid_file)
        assert pid_file.exists()
