# InkArms Hub

The Hub is an always-on local daemon that keeps platform adapters running, exposes a REST + WebSocket API, runs scheduled AI jobs, accepts webhook triggers, and optionally acts as an OpenAI-compatible proxy.

---

## Quick Start

```bash
# Install hub dependencies
pip install "inkarms[hub]"

# Start in background
inkarms hub start --background

# Check status
inkarms hub status

# Stop
inkarms hub stop
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `inkarms hub start` | Start hub in foreground (Ctrl+C to stop) |
| `inkarms hub start --background` | Start in background; tail log for output |
| `inkarms hub stop` | Stop gracefully via SIGTERM (or `launchctl unload` if service-installed) |
| `inkarms hub restart` | Stop then start |
| `inkarms hub status` | Show uptime, model, today's cost |
| `inkarms hub logs` | Print last 50 lines of hub.log |
| `inkarms hub logs --follow` | Stream new log lines (Ctrl+C to stop) |
| `inkarms hub logs --lines 100` | Print last N lines |
| `inkarms hub install` | Install as launchd (macOS) or systemd (Linux) service |
| `inkarms hub uninstall` | Remove the system service |
| `inkarms hub key` | Show current API key |
| `inkarms hub key --rotate` | Generate and store a new API key |
| `inkarms hub dev` | Start with `--reload` for development |

---

## Configuration

Add a `hub` section to your `~/.inkarms/config.yaml`:

```yaml
hub:
  enable: true
  host: "127.0.0.1"      # Never expose to 0.0.0.0 without a reverse proxy
  port: 18750
  trust_localhost: true   # Skip auth for 127.0.0.1/::1 connections
  tool_approval_mode: auto   # "auto" or "disabled"
  openai_proxy: false    # Set true to enable /v1/chat/completions
  auto_start_platforms: true
  shutdown_timeout: 30
```

Full schema: see `HubConfig` in `src/inkarms/config/schema.py`.

> **Note:** `trust_localhost: true` means any local process can call the hub without an API key. Set to `false` on shared systems (VPS, cloud VMs, Docker hosts).

---

## Authentication

### HTTP Requests

All endpoints except `GET /health` require authentication.

**Bearer token:**
```
Authorization: Bearer <key>
```

**Custom header:**
```
X-InkArms-Key: <key>
```

Get the key: `inkarms hub key`

### WebSocket Connections

WebSocket endpoints use **first-message authentication** — no `?token=` query parameter (query strings appear in access logs).

```
WS /ws/chat/{session_id}
Client → Server: {"type": "auth", "token": "<key>"}   ← must arrive within 5 seconds
Server → Client: {"type": "ready"}                     ← proceed
  OR
Server → Client: {"type": "error", "message": "unauthorized"} + close(1008)
```

> Keys are stored as SHA-256 hashes and compared with `hmac.compare_digest` (constant-time — prevents timing attacks).

### Rate Limiting

Failed authentication attempts are tracked per IP in a sliding window. After `auth_max_failures` failures (default: 20) within `auth_window_seconds` (default: 60s), the IP is locked out for `auth_lockout_seconds` (default: 300s). Lockout state is in-memory and resets on hub restart.

---

## REST Endpoints

### Health & Status

```
GET  /health          → {"status": "ok", "version": "..."}   (unauthenticated)
GET  /api/status      → uptime, model, budget summary
GET  /api/budget      → daily limit, today's cost, enforcement flag
```

### Sessions

```
GET    /api/sessions                       List all sessions (paginated)
GET    /api/sessions?platform=hub          Filter by platform
GET    /api/sessions?limit=50&offset=0     Pagination
GET    /api/sessions/{session_id}          Session detail + recent turns
DELETE /api/sessions/{session_id}          Remove session from DB + delete JSON files
```

Session metadata is stored in `hub.db` (`session_index` table). Conversation turns are stored in JSON daily files under `~/.inkarms/memory/platform/`.

### Platforms

```
GET /api/platforms    Health check for each connected platform adapter
```

### Cron Jobs

```
GET    /api/cron                  List all cron jobs
GET    /api/cron/{id}             Get one job (includes last_run, run_count)
POST   /api/cron                  Create a new job
DELETE /api/cron/{id}             Delete a job
PATCH  /api/cron/{id}/enable      Enable or disable a job
```

See [hub-cron.md](./hub-cron.md) for the full reference.

### Budget

```
GET /api/budget    → {daily_limit, today_cost, block_on_exceed, ...}
```

---

## WebSocket Endpoints

### Chat (`/ws/chat/{session_id}`)

Full bidirectional chat with streaming tool execution. Maps to `MessageProcessor.process_streaming()`.

**Message protocol (after auth):**

```
Client → Server: {"type": "message", "content": "list my git branches"}
Server → Client: {"type": "delta", "content": "Here are your branches: "}
Server → Client: {"type": "tool_start", "name": "bash", "input": "git branch -a"}
Server → Client: {"type": "tool_done", "name": "bash", "output": "* main\n  feat/hub\n"}
Server → Client: {"type": "delta", "content": "main and feat/hub."}
Server → Client: {"type": "done", "tokens": 312, "cost": 0.0004}
Server → Client: {"type": "ping"}    ← server-side heartbeat every 30s
```

The session is persistent: send multiple messages on the same connection to build a conversation. The `session_id` in the URL maps to a `platform="hub"` row in `session_index`.

**Skill injection:**

```json
{"type": "message", "content": "review this PR", "skills": ["code-review"]}
```

### Events (`/ws/events`)

Subscribe to all hub events (platform messages, cron job runs, trigger fires, shutdown).

```
Server → Client: {"type": "shutdown"}           ← hub is stopping
Server → Client: {"type": "overflow", "dropped": 3}  ← queue full (3 events dropped)
```

Each subscriber gets a bounded queue (maxsize=1000). If the queue is full, the oldest event is dropped and an `overflow` frame is sent. After 3 consecutive overflows the connection is closed. Maximum concurrent subscribers: `hub.max_event_subscribers` (default: 50).

### Logs (`/ws/logs`)

Streams new lines from `hub.log` as they are written. Handles log rotation via inode-change detection.

```
Server → Client: {"type": "log", "line": "2026-02-20 10:00:01 INFO hub started"}
```

Requires `aiofiles`: included in `pip install inkarms[hub]`.

---

## OpenAI-Compatible Proxy

When `hub.openai_proxy: true`, the hub exposes a drop-in OpenAI endpoint usable by Continue.dev, Open WebUI, shell scripts, etc.

```
POST /v1/chat/completions
```

**Streaming (SSE):**

```bash
curl http://127.0.0.1:18750/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}], "stream": true}'
```

**Non-streaming:**

```bash
curl http://127.0.0.1:18750/v1/chat/completions \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]}'
```

Streaming responses include `X-Accel-Buffering: no` to disable nginx proxy buffering. The `[DONE]` sentinel is passed through as-is (it is not valid JSON — do not parse it).

---

## Service Installation

### macOS (launchd)

```bash
inkarms hub install
# Starts automatically at login, restarts on crash
# Logs: ~/.inkarms/logs/hub.log

inkarms hub status
# Running on 127.0.0.1:18750 — uptime=42s model=claude-sonnet-4-6

inkarms hub stop       # Uses launchctl unload (not SIGTERM — avoids immediate restart)
inkarms hub uninstall  # Removes plist + sentinel
```

The plist is written to `~/Library/LaunchAgents/dev.inkarms.hub.plist` with:
- `KeepAlive.SuccessfulExit = false` — restart on crash, not on clean exit
- `ThrottleInterval = 10` — 10s minimum between restarts (prevents CPU spin on bad config)
- `PYTHONUNBUFFERED = 1` — ensures log lines appear immediately

### Linux (systemd)

```bash
inkarms hub install
# Equivalent to:
# systemctl --user daemon-reload
# systemctl --user enable inkarms-hub.service
# systemctl --user start inkarms-hub.service

# Check status
systemctl --user status inkarms-hub.service

# Follow logs
journalctl --user -u inkarms-hub.service -f

inkarms hub uninstall
```

The unit file is written to `~/.config/systemd/user/inkarms-hub.service`.

---

## SIGHUP Config Reload

Send SIGHUP to reload configuration without full restart:

```bash
kill -HUP $(cat ~/.inkarms/hub.pid)
```

Reload behaviour:
1. Validates new config — aborts and keeps old config on any error (zero downtime)
2. Syncs budget tracker to DB
3. If platform adapters are running: stops and restarts them with new config (brief message-drop window)
4. If adapters newly enabled in new config: starts them
5. Active WebSocket sessions continue with old config until reconnection

---

## Budget Enforcement

```yaml
cost:
  budgets:
    daily: 5.0    # USD — enforced
  alerts:
    block_on_exceed: true   # Return HTTP 429 when exceeded
```

The hub maintains an in-memory `BudgetTracker` that reads today's accumulated cost from `hub.db` on startup and syncs every `budget_sync_interval` seconds (default: 60). This means zero DB queries on the hot path.

> **Known limitation:** `budgets.weekly` and `budgets.monthly` are **not enforced** — only `budgets.daily` works. Setting weekly/monthly logs a warning.

---

## SQLite Schema (`hub.db`)

`hub.db` lives at `~/.inkarms/hub.db` (separate from `data.db` used by the core storage layer).

| Table | Contents |
|-------|----------|
| `session_index` | Platform sessions — fast REST queries |
| `cron_jobs` | Scheduled job definitions |
| `daily_cost` | Daily accumulated cost for BudgetTracker |
| `schema_version` | Migration tracking |

WAL mode is enabled for concurrent readers + single writer. A background task runs `PRAGMA wal_checkpoint(PASSIVE)` every 5 minutes to bound WAL file size.

---

## Known Limitations

- **Auth lockout resets on restart** — in-memory sliding window; a local attacker who can restart the hub resets lockout state.
- **Weekly/monthly budget limits not enforced** — only `budgets.daily` has an effect.
- **SIGHUP message gap** — platform adapters are briefly stopped during reload. Messages received in that window are silently dropped.
- **APScheduler pinned to v3** — `apscheduler<4.0`. When v4 reaches stable, a deliberate migration will be needed.
