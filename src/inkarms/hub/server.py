"""
Hub uvicorn server management.

Provides port availability check and uvicorn launch helpers used by
``inkarms hub start``.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def check_port_available(host: str, port: int) -> bool:
    """Return True if (host, port) is available to bind.

    Uses a real bind() attempt so the result reflects the OS state at call
    time (avoids TOCTOU between check and actual bind, but good enough for a
    friendly error message).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def start_background(
    host: str,
    port: int,
    log_path: Path,
    *,
    reload: bool = False,
) -> subprocess.Popen:  # type: ignore[type-arg]
    """Launch uvicorn as a background subprocess.

    Stdout and stderr are redirected to log_path (appended).
    Returns the Popen object for the caller to track.

    Note: --ws-per-message-deflate false prevents per-message memory bloat
    when many WS connections are open.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a")

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "inkarms.hub.app:app",
        "--host",
        host,
        "--port",
        str(port),
        "--ws-per-message-deflate",
        "false",
    ]
    if reload:
        cmd.append("--reload")

    process = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=log_file,
        stderr=log_file,
        # Detach from parent's process group so Ctrl+C in CLI doesn't kill hub
        start_new_session=True,
    )
    logger.debug("Hub uvicorn started pid=%d cmd=%s", process.pid, " ".join(cmd))
    return process


def wait_for_ready(host: str, port: int, timeout: float = 10.0) -> bool:
    """Poll /health until the hub responds or timeout elapses.

    Returns True if the hub is ready within the timeout.
    """
    import time

    import httpx

    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/health"
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.5)
    return False
