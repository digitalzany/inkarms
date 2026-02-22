"""
Hub PID file management.

Uses O_EXCL atomic creation to prevent race conditions. Stale PID files are
detected via kill -0 and overwritten (never unlinked — see acquire() docstring).
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path


class HubAlreadyRunningError(Exception):
    """Raised when a live hub process already holds the PID file."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        super().__init__(f"Hub is already running with PID {pid}")


class HubPIDError(Exception):
    """Raised when PID file acquisition fails after max retries."""


MAX_ACQUIRE_RETRIES = 3


def acquire(path: Path, _retry: int = 0) -> None:
    """Atomically create the hub PID file.

    Raises HubAlreadyRunningError if another live hub process holds the file.
    Raises HubPIDError if acquisition fails after MAX_ACQUIRE_RETRIES attempts.

    PID files are NEVER deleted on exit — only overwritten when a stale file is
    detected. Deleting creates a race with OS PID reuse: process A deletes,
    OS reuses PID, process B creates a file with the same PID, process C thinks
    it is the only instance. Overwriting avoids this window.

    Also installs a SIGTERM → sys.exit(0) bridge so that FastAPI lifespan
    teardown (the ``yield`` cleanup) runs on SIGTERM.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        # Bridge SIGTERM → sys.exit(0) so FastAPI lifespan cleanup runs.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except FileExistsError:
        pid = _read_pid(path)
        if _is_stale(pid):
            if _retry >= MAX_ACQUIRE_RETRIES:
                raise HubPIDError("Failed to acquire PID file after retries")
            # Overwrite stale PID file directly (no unlink — avoid race window).
            # After overwriting, check again that the file is still ours before
            # proceeding (guard against a concurrent acquire).
            path.write_text(str(os.getpid()))
            # Verify the file now contains our PID (another process may have
            # raced us). If not, recurse to retry.
            if _read_pid(path) != os.getpid():
                acquire(path, _retry + 1)
            else:
                signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        else:
            raise HubAlreadyRunningError(pid)


def read(path: Path) -> int | None:
    """Read the PID from the PID file.

    Returns None if the file does not exist or contains an invalid PID.
    """
    return _read_pid(path) if path.exists() else None


def _read_pid(path: Path) -> int:
    """Read integer PID from file. Returns 0 on parse error."""
    try:
        return int(path.read_text().strip())
    except (ValueError, OSError):
        return 0


def _is_stale(pid: int) -> bool:
    """Return True if no live process holds this PID."""
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return False
    except (OSError, ProcessLookupError):
        return True
