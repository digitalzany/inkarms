# Hub Cron Jobs

The hub can run scheduled AI queries and bash commands using APScheduler v3. Jobs are persisted in `hub.db` and survive hub restarts.

---

## Quick Start

```bash
# Create a bash job that runs every 5 minutes
curl -X POST http://127.0.0.1:18750/api/cron \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "disk-check",
    "schedule": "every 5m",
    "type": "bash",
    "command": "df -h / | tail -1"
  }'

# Create an AI query job that runs daily at 9am
curl -X POST http://127.0.0.1:18750/api/cron \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "daily-summary",
    "schedule": "0 9 * * *",
    "type": "ai_query",
    "command": "Summarise my git activity from the last 24 hours.",
    "session_id": "daily-reports"
  }'

# List all jobs
curl -H "Authorization: Bearer $KEY" http://127.0.0.1:18750/api/cron

# Delete a job
curl -X DELETE -H "Authorization: Bearer $KEY" http://127.0.0.1:18750/api/cron/disk-check
```

---

## Job Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id` | `str` | required | Unique identifier (1-128 chars) |
| `schedule` | `str` | required | Cron expression or interval shorthand |
| `type` | `"bash" \| "ai_query"` | `"bash"` | Job type |
| `command` | `str` | required | Bash command or AI prompt |
| `session_id` | `str` | `"default"` | Session context for `ai_query` jobs |
| `notify` | `str \| null` | `null` | Not yet implemented — reserved for future use |
| `enabled` | `bool` | `true` | Enable or disable without deleting |

---

## Schedule Syntax

### Interval Shorthand

Simple intervals use the `every N<unit>` format:

| Schedule | Meaning |
|----------|---------|
| `every 30s` | Every 30 seconds |
| `every 5m` | Every 5 minutes |
| `every 2h` | Every 2 hours |
| `every 1d` | Every 1 day |

Unit letters: `s` (seconds), `m` (minutes), `h` (hours), `d` (days). Case-insensitive.

### Cron Expressions

Standard 5-field cron syntax (minute, hour, day-of-month, month, day-of-week):

```
┌───────── minute (0-59)
│ ┌─────── hour (0-23)
│ │ ┌───── day of month (1-31)
│ │ │ ┌─── month (1-12)
│ │ │ │ ┌─ day of week (0-6, 0=Sunday)
│ │ │ │ │
* * * * *
```

**Examples:**

| Expression | Runs at |
|------------|---------|
| `0 9 * * *` | 9:00 AM every day |
| `0 9 * * 1` | 9:00 AM every Monday |
| `*/15 * * * *` | Every 15 minutes |
| `0 0 1 * *` | Midnight on the 1st of every month |
| `30 17 * * 5` | 5:30 PM every Friday |

6-field cron (with seconds as first field) is also accepted.

---

## Job Types

### `type: bash`

Runs the `command` string through InkArms's `SandboxExecutor`. The sandbox applies the same whitelist and path restrictions as the CLI.

```json
{
  "id": "cleanup",
  "schedule": "every 1h",
  "type": "bash",
  "command": "find /tmp -name '*.tmp' -mtime +1 -delete"
}
```

- Runs in a thread pool (`asyncio.to_thread`) — does not block the event loop
- Sandbox respects `security.whitelist` and `security.path_restrictions` from config
- Output is truncated to 500 characters in `last_result`
- Exit code != 0 is recorded as `EXIT N: <stderr>`

### `type: ai_query`

Runs `command` as a natural-language prompt through `MessageProcessor.process()`. Uses the session specified by `session_id` for conversation context.

```json
{
  "id": "weekly-report",
  "schedule": "0 9 * * 1",
  "type": "ai_query",
  "command": "Review the git log for the past week and write a brief summary of what was accomplished.",
  "session_id": "weekly-reports"
}
```

By default, `ai_query` jobs run with **no tool access** (`cron_tool_approval_mode: disabled`). This is intentional — headless AI jobs should not silently modify files or run commands.

To allow tool use:

```yaml
hub:
  cron_tool_approval_mode: auto   # All tools enabled for ai_query cron jobs
```

---

## API Reference

### List Jobs

```
GET /api/cron
```

```json
{
  "jobs": [
    {
      "id": "disk-check",
      "schedule": "every 5m",
      "type": "bash",
      "command": "df -h / | tail -1",
      "session_id": "default",
      "enabled": true,
      "last_run": "2026-02-20T09:55:00",
      "last_result": "Filesystem  Size  Used Avail Use% Mounted on\n/dev/disk1  500G  210G  290G  42% /",
      "run_count": 42
    }
  ],
  "total": 1
}
```

### Get Job

```
GET /api/cron/{id}
```

### Create Job

```
POST /api/cron
Content-Type: application/json

{
  "id": "my-job",
  "schedule": "every 10m",
  "type": "bash",
  "command": "date"
}
```

Returns `201 Created` with the created job. Returns `409 Conflict` if the ID already exists. Returns `422 Unprocessable Entity` if the schedule string is invalid.

### Delete Job

```
DELETE /api/cron/{id}
```

Returns `200 {"status": "deleted", "id": "my-job"}` or `404` if not found.

### Enable / Disable Job

```
PATCH /api/cron/{id}/enable
Content-Type: application/json

{"enabled": false}
```

Disabling a job removes it from APScheduler but keeps the record in `hub.db`. Re-enabling re-registers it.

---

## Persistence

Jobs are stored in the `cron_jobs` table of `hub.db`. On hub restart, all enabled jobs are re-loaded from the database and re-registered with APScheduler. APScheduler's internal job store is not used for persistence — `hub.db` is the single source of truth.

---

## Security Model

All bash cron jobs run inside the `SandboxExecutor`, which enforces:

- Command whitelist (configured in `security.whitelist`)
- Path restrictions (blocks access to `~/.ssh`, `~/.aws`, etc. by default)
- No network access restrictions by default (configure firewall separately)

`ai_query` jobs use `cron_tool_approval_mode` (default: `disabled`). With `disabled`, the AI receives no tools and can only generate text. Set to `auto` only if you trust the prompts in your cron jobs to run arbitrary tools.

---

## Known Limitations

- **APScheduler v3 only** — pinned to `apscheduler<4.0`. APScheduler v4 is a breaking rewrite; migration will be needed deliberately when it reaches stable.
- **`max_instances: 1`** — each job has a single-instance guard. If a run takes longer than the schedule interval, the next run is skipped rather than overlapping. The skipped run is logged at WARNING level.
- **`notify` field** — reserved for future reply-routing (Telegram, Slack, etc.). Currently has no effect.
