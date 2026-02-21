"""
inkarms hub CLI commands.

Commands:
    inkarms hub start     Start the hub daemon (foreground unless --background)
    inkarms hub stop      Send SIGTERM (or launchctl unload if installed)
    inkarms hub restart   Stop then start
    inkarms hub status    Connect to /health + /api/status
    inkarms hub logs      Tail hub.log (last N lines; --follow for live)
    inkarms hub install   Write launchd/systemd service and enable
    inkarms hub uninstall Remove and disable the system service
    inkarms hub key       Show or rotate the hub API key
    inkarms hub dev       Start with uvicorn --reload (dev only)

FastAPI/uvicorn are optional dependencies — all commands guard against
ImportError and show a helpful install hint.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="hub",
    help="Manage the InkArms Hub always-on daemon.",
    no_args_is_help=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_hub_deps() -> None:
    """Raise UsageError with install hint if hub dependencies are missing."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise typer.BadParameter(
            f"Hub dependencies missing: {exc}\n"
            "Install with: pip install inkarms[hub]"
        ) from exc


def _get_config():  # type: ignore[return]
    """Load config, returning None on failure."""
    try:
        from inkarms.config.loader import get_config

        return get_config()
    except Exception:  # noqa: BLE001
        return None


def _hub_url(host: str = "127.0.0.1", port: int = 18750) -> str:
    return f"http://{host}:{port}"


def _read_pid() -> int | None:
    """Return hub PID if a live PID file exists, else None."""
    from inkarms.hub.pid import read as pid_read
    from inkarms.storage.paths import get_hub_pid_path

    return pid_read(get_hub_pid_path())


def _is_running(host: str, port: int) -> bool:
    """Return True if hub /health responds within 1 second."""
    try:
        import httpx

        resp = httpx.get(f"http://{host}:{port}/health", timeout=1.0)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _find_pid_by_port(port: int) -> int | None:
    """Return the PID of the process listening on *port*, or None.

    Uses ``lsof -ti TCP:<port> -sTCP:LISTEN`` which is available on both
    macOS and most Linux distributions without extra dependencies.
    """
    import subprocess

    try:
        result = subprocess.run(  # noqa: S603 S607
            ["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        pid_str = result.stdout.strip()
        # lsof may return multiple PIDs (one per line) — take the first
        first = pid_str.splitlines()[0] if pid_str else ""
        return int(first) if first.isdigit() else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def start(
    background: Annotated[
        bool,
        typer.Option("--background", "-b", help="Run hub in background."),
    ] = False,
) -> None:
    """Start the InkArms Hub daemon."""
    _require_hub_deps()

    cfg = _get_config()
    host = cfg.hub.host if cfg else "127.0.0.1"
    port = cfg.hub.port if cfg else 18750

    from inkarms.hub.server import check_port_available
    from inkarms.storage.paths import get_hub_log_path, get_hub_pid_path

    if not check_port_available(host, port):
        typer.echo(f"[hub] Port {port} is already in use. Is the hub already running?")
        raise typer.Exit(1)

    if background:
        from inkarms.hub.server import start_background, wait_for_ready

        log_path = get_hub_log_path()
        proc = start_background(host, port, log_path)

        # Write PID file so 'hub stop' can SIGTERM the background process.
        # (Foreground mode writes this via acquire(); background bypasses that path.)
        pid_path = get_hub_pid_path()
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(proc.pid))

        typer.echo(f"[hub] Starting in background (pid={proc.pid}, log={log_path})…")
        if wait_for_ready(host, port, timeout=10.0):
            typer.echo(f"[hub] Running at http://{host}:{port}")
        else:
            typer.echo(f"[hub] Hub did not respond within 10s — check {log_path}")
            raise typer.Exit(1)
    else:
        # Foreground: acquire PID file and run uvicorn directly
        from inkarms.hub.pid import HubAlreadyRunningError, acquire

        try:
            acquire(get_hub_pid_path())
        except HubAlreadyRunningError as exc:
            typer.echo(f"[hub] Already running (pid={exc.pid})")
            raise typer.Exit(1) from exc

        typer.echo(f"[hub] Starting foreground on http://{host}:{port} (Ctrl+C to stop)")
        try:
            import uvicorn

            uvicorn.run(
                "inkarms.hub.app:app",
                host=host,
                port=port,
                ws_per_message_deflate=False,
                log_level="info",
            )
        except KeyboardInterrupt:
            typer.echo("\n[hub] Stopped.")


@app.command()
def stop() -> None:
    """Stop the running Hub daemon."""
    from inkarms.storage.paths import get_hub_pid_path, get_inkarms_home

    # Check for launchd-managed mode first
    sentinel = get_inkarms_home() / "hub.launchd"
    if sentinel.exists():
        plist_path = sentinel.read_text().strip()
        typer.echo(f"[hub] Stopping via launchctl (managed service)…")
        os.system(f"launchctl unload '{plist_path}'")  # noqa: S605
        return

    pid = _read_pid()
    if pid is None:
        # No PID file — try to find the process by port before giving up
        cfg = _get_config()
        port = cfg.hub.port if cfg else 18750
        pid = _find_pid_by_port(port)
        if pid is None:
            typer.echo("[hub] No PID file and no process found on port — hub is not running.")
            raise typer.Exit(1)
        typer.echo(f"[hub] No PID file — found hub process via port {port} (pid={pid})")

    try:
        os.kill(pid, signal.SIGTERM)
        typer.echo(f"[hub] Sent SIGTERM to pid={pid}")
    except ProcessLookupError:
        # PID file was stale — try port-based discovery as last resort
        cfg = _get_config()
        port = cfg.hub.port if cfg else 18750
        fallback_pid = _find_pid_by_port(port)
        if fallback_pid:
            os.kill(fallback_pid, signal.SIGTERM)
            typer.echo(f"[hub] Sent SIGTERM to pid={fallback_pid} (found via port {port})")
        else:
            typer.echo(f"[hub] PID {pid} not found and no process on port {port} — hub is not running.")
            raise typer.Exit(1)


@app.command()
def restart() -> None:
    """Restart the Hub daemon."""
    stop()
    start()


@app.command()
def status() -> None:
    """Show hub status (uptime, cost, model)."""
    cfg = _get_config()
    host = cfg.hub.host if cfg else "127.0.0.1"
    port = cfg.hub.port if cfg else 18750

    try:
        import httpx

        resp = httpx.get(f"http://{host}:{port}/health", timeout=2.0)
        if resp.status_code != 200:
            typer.echo(f"[hub] Not responding (status {resp.status_code})")
            raise typer.Exit(1)

        # Try authenticated /api/status
        api_key = _get_api_key(cfg)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp2 = httpx.get(f"http://{host}:{port}/api/status", headers=headers, timeout=2.0)
        if resp2.status_code == 200:
            data = resp2.json()
            uptime = data.get("uptime_seconds", 0)
            typer.echo(
                f"[hub] Running on {host}:{port} — "
                f"uptime={uptime:.0f}s model={data.get('model', '?')}"
            )
            budget = data.get("budget", {})
            if budget.get("today_cost") is not None:
                typer.echo(
                    f"[hub] Today cost=${budget['today_cost']:.4f} "
                    f"limit={budget.get('daily_limit')}"
                )
        else:
            typer.echo(f"[hub] Running (unauthenticated — /api/status returned {resp2.status_code})")

    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[hub] Not reachable: {exc}")
        raise typer.Exit(1)


@app.command()
def logs(
    lines: Annotated[int, typer.Option("--lines", "-n", help="Last N lines.")] = 50,
    follow: Annotated[bool, typer.Option("--follow", "-f", help="Stream new lines.")] = False,
) -> None:
    """Tail the hub log file."""
    from inkarms.storage.paths import get_hub_log_path

    log_path = get_hub_log_path()
    if not log_path.exists():
        typer.echo(f"[hub] Log file not found: {log_path}")
        raise typer.Exit(1)

    # Show last N lines
    all_lines = log_path.read_text().splitlines()
    for line in all_lines[-lines:]:
        typer.echo(line)

    if follow:
        import time

        typer.echo(f"[hub] Following {log_path} (Ctrl+C to stop)…")
        try:
            with log_path.open() as f:
                f.seek(0, 2)  # Seek to end
                while True:
                    line = f.readline()
                    if line:
                        typer.echo(line, nl=False)
                    else:
                        time.sleep(0.2)
        except KeyboardInterrupt:
            pass


@app.command()
def install() -> None:
    """Install hub as a launchd (macOS) or systemd (Linux) service."""
    import platform as _platform
    import shutil

    from inkarms.storage.paths import get_hub_log_path, get_inkarms_home

    plat = _platform.system()
    inkarms_bin = shutil.which("inkarms") or sys.executable + " -m inkarms"
    python_bin = sys.executable

    if plat == "Darwin":
        _install_launchd(python_bin, get_hub_log_path(), get_inkarms_home())
    elif plat == "Linux":
        _install_systemd(inkarms_bin)
    else:
        typer.echo(f"[hub] Unsupported platform for service install: {plat}")
        raise typer.Exit(1)


@app.command()
def uninstall() -> None:
    """Remove the hub system service."""
    import platform as _platform

    plat = _platform.system()
    if plat == "Darwin":
        _uninstall_launchd()
    elif plat == "Linux":
        _uninstall_systemd()
    else:
        typer.echo(f"[hub] Unsupported platform: {plat}")
        raise typer.Exit(1)


@app.command()
def key(
    rotate: Annotated[bool, typer.Option("--rotate", help="Generate a new API key.")] = False,
) -> None:
    """Show or rotate the hub API key."""
    cfg = _get_config()
    key_name = cfg.hub.api_key_name if cfg else "hub_api_key"

    try:
        from inkarms.secrets.manager import SecretsManager

        sm = SecretsManager()
        if rotate:
            import secrets

            new_key = secrets.token_hex(32)
            sm.set(key_name, new_key)
            typer.echo(f"[hub] New API key stored under '{key_name}'.")
            typer.echo(f"[hub] Key: {new_key}")
            typer.echo("[hub] Restart the hub for the new key to take effect.")
        else:
            existing = sm.get(key_name)
            if existing:
                typer.echo(f"[hub] API key ({key_name}): {existing}")
            else:
                typer.echo(f"[hub] No key stored under '{key_name}'. Run: inkarms hub key --rotate")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[hub] SecretsManager error: {exc}")
        raise typer.Exit(1)


@app.command()
def dev() -> None:
    """Start hub with uvicorn --reload (development only)."""
    _require_hub_deps()

    cfg = _get_config()
    host = cfg.hub.host if cfg else "127.0.0.1"
    port = cfg.hub.port if cfg else 18750

    typer.echo(f"[hub] Dev mode — http://{host}:{port}  (SIGTERM unreliable in --reload mode)")

    import uvicorn

    uvicorn.run(
        "inkarms.hub.app:app",
        host=host,
        port=port,
        reload=True,
        ws_per_message_deflate=False,
        log_level="debug",
    )


# ---------------------------------------------------------------------------
# Service installation helpers
# ---------------------------------------------------------------------------


def _install_launchd(python_bin: str, log_path: Path, inkarms_home: Path) -> None:
    """Write and load a launchd plist for macOS."""
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "dev.inkarms.hub.plist"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.inkarms.hub</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python_bin}</string>
    <string>-m</string>
    <string>inkarms</string>
    <string>hub</string>
    <string>start</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>
  </dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>StandardOutPath</key><string>{log_path}</string>
  <key>StandardErrorPath</key><string>{log_path}</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content)
    typer.echo(f"[hub] Wrote launchd plist: {plist_path}")

    # Write sentinel so 'hub stop' knows to use launchctl
    sentinel = inkarms_home / "hub.launchd"
    sentinel.write_text(str(plist_path))

    os.system(f"launchctl load '{plist_path}'")  # noqa: S605
    typer.echo("[hub] Service loaded. Run: inkarms hub status")


def _install_systemd(inkarms_bin: str) -> None:
    """Write and enable a systemd user service for Linux."""
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_path = service_dir / "inkarms-hub.service"

    service_content = f"""[Unit]
Description=InkArms Hub
After=network.target

[Service]
Type=simple
ExecStart={inkarms_bin} hub start
Restart=on-failure
RestartSec=5
EnvironmentFile=-%h/.inkarms/hub.env
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""
    service_path.write_text(service_content)
    typer.echo(f"[hub] Wrote systemd unit: {service_path}")

    os.system("loginctl enable-linger $USER")  # noqa: S605
    os.system("systemctl --user daemon-reload")  # noqa: S605
    os.system("systemctl --user enable inkarms-hub.service")  # noqa: S605
    os.system("systemctl --user start inkarms-hub.service")  # noqa: S605
    typer.echo("[hub] Service enabled. Check: systemctl --user status inkarms-hub.service")
    typer.echo("[hub] Logs: journalctl --user -u inkarms-hub.service -f")


def _uninstall_launchd() -> None:
    from inkarms.storage.paths import get_inkarms_home

    plist_path = Path.home() / "Library" / "LaunchAgents" / "dev.inkarms.hub.plist"
    if plist_path.exists():
        os.system(f"launchctl unload '{plist_path}'")  # noqa: S605
        plist_path.unlink()
        typer.echo(f"[hub] Removed: {plist_path}")
    sentinel = get_inkarms_home() / "hub.launchd"
    if sentinel.exists():
        sentinel.unlink()


def _uninstall_systemd() -> None:
    os.system("systemctl --user stop inkarms-hub.service")  # noqa: S605
    os.system("systemctl --user disable inkarms-hub.service")  # noqa: S605
    service_path = Path.home() / ".config" / "systemd" / "user" / "inkarms-hub.service"
    if service_path.exists():
        service_path.unlink()
        typer.echo(f"[hub] Removed: {service_path}")
    os.system("systemctl --user daemon-reload")  # noqa: S605


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _get_api_key(cfg: Any) -> str | None:
    """Try to read hub API key from SecretsManager."""
    try:
        from inkarms.secrets.manager import SecretsManager

        key_name = cfg.hub.api_key_name if cfg else "hub_api_key"
        return SecretsManager().get(key_name)
    except Exception:  # noqa: BLE001
        return None
