# Changelog

All notable changes to InkArms will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **`auto_discover_models` config flag** — `providers.auto_discover_models: false` (default off).
  When enabled, InkArms fetches the live model list from each provider's API on startup and
  merges newly-discovered models into `~/.inkarms/providers.yaml`. Exposed in the config wizard
  (Provider Setup step). Set to `false` by default so users who manage a curated list are unaffected.
- **OpenAI model discovery** — `_OpenAIFetcher` added to the background updater registry.
  Non-chat model families (dall-e, whisper, tts, embeddings, etc.) are excluded automatically.
  New chat model families are included without any code change.
- **File logging** — `~/.inkarms/logs/inkarms.log` created at CLI startup via a rotating file
  handler (10 MB per file, 3 backups). All `inkarms.*` loggers write at DEBUG level.
- **Tools sub-menu in the Advanced config wizard** — Web Search is now grouped under a "Tools"
  section (mirroring the "Platforms" pattern) rather than being a top-level Advanced menu item.
- **Config wizard: model discovery toggle** — New "Model Discovery" screen in the Provider Setup
  step lets users enable/disable `auto_discover_models` during wizard setup.

### Changed
- **Background model updater now runs for all entry points** — `get_config()` spawns the updater
  thread on first call (guarded by `_updater_started` flag), so model discovery fires
  automatically when starting the CLI, the hub daemon, or platform adapters. Previously it only
  ran from `RichBackend.initialize()`.
- **Model reloads immediately after wizard save** — Saving the config wizard now clears the
  config cache and reloads the active model in the current UI session. No restart needed.

### Fixed
- **Audit log path** — Default path corrected from `~/.inkarms/audit.jsonl` to
  `~/.inkarms/audit/audit.jsonl` across the schema, documentation, and example configs.
- **Audit logger: buffered events lost on exit** — Added `atexit.register(self.flush)` so the
  in-memory buffer is always flushed when the process exits.
- **Audit logger not wired to sandbox** — Both sandbox call sites (`run.py` and `backend.py`)
  now pass `get_audit_logger()` to `SandboxExecutor.from_config()`.
- **Config wizard Back button stuck at first step** — When the history stack was empty,
  the engine now resets to the WelcomeStep so users can switch between Quick/Advanced modes.
- **Background model updater: wrong secret key lookup** — `_get_api_key()` now tries the
  provider ID first (e.g. `"anthropic"`, as stored by the wizard) before falling back to the
  lower-cased env-var name. Previously no keys were found, so the updater silently did nothing.
- **Providers cache not cleared after model discovery** — `_update_user_config()` now calls
  `clear_providers_cache()` after writing `providers.yaml`, so the config wizard immediately
  shows newly-discovered models.
- **"Configuration saved" appearing in chat** — Summary and Advanced menu save confirmations
  now log at INFO level instead of calling `display_info()`, keeping the chat view clean.
- **Telegram: `/models` command replied with "Message is too long"** — `_handle_command()`
  now routes responses longer than 4096 characters through `_send_split_message()`.

---

## [0.11.0] - 2026-02-24

### Added

#### Configuration Wizard (Engine Refactor)
- **`WizardEngine`** — Drives wizard step flow with a history-stack for back navigation.
  After the WelcomeStep sets the mode, only applicable steps run. Back at step zero restarts
  from WelcomeStep so the user can switch Quick ↔ Advanced.
- **`WizardStep` ABC** — Abstract base class for all steps. Each step declares `step_key`,
  optional `modes` restriction, and `run()`. Adding a new step is one file + one line in
  `build_steps()`.
- **Modular step registry** — Ten step files under `config/wizard/steps/`:
  `welcome`, `provider`, `security`, `tool_secrets`, `tools`, `agent`, `context`, `cost`,
  `hub`, `platforms`, `advanced_menu`, `summary`.
- **Advanced mode non-linear menu** (`AdvancedMenuStep`) — Section picker that shows current
  values inline. Users jump into any section, configure it, and return without losing changes.
  Sections: Provider, Security, Tools, Agent, Context, Cost, Hub, Platforms.
- **Platform tokens encrypted via SecretsManager** — Keys stored under
  `<platform>_<field>` (e.g. `telegram_token`), never in plaintext config.

#### Background Model Discovery
- **Model updater refactored** (`config/updater.py`) — Extensible ABC registry pattern:
  `_HttpFetcher` base class for remote providers, `_LocalFetcher` for local services.
  Adding a new provider is one subclass + one registry entry.
- **Anthropic model discovery** — Fetches live model list via `/v1/models`.
- **Gemini model discovery** — Fetches via Google AI REST API (key in query param).
- **Ollama model discovery** — Lists locally-running models via the `ollama` Python package
  (imported lazily; skipped if not installed).
- **Provider model merging** — Discovered models are appended to `~/.inkarms/providers.yaml`
  (new IDs only; existing entries are never modified or removed). The in-process cache is
  invalidated after each write.

#### Hub Daemon
- **FastAPI daemon** (`inkarms hub start/stop/status/restart`) on `127.0.0.1:18750` by default.
  Runs as a background process tracked by a PID file.
- **System service install** (`inkarms hub install`) — Installs as a launchd/systemd service
  for auto-start at login.
- **REST API endpoints**:
  - `GET /api/status` — Daemon health, uptime, platform status
  - `GET /api/sessions`, `POST /api/sessions` — Session management
  - `GET /api/budget` — Daily/weekly/monthly cost totals
  - `GET/POST/DELETE /api/cron` — Manage scheduled jobs
  - `POST /triggers/{name}` — Fire AI actions from HTTP sources (GitHub, CI, etc.)
  - `GET/POST /api/platforms` — Platform adapter control
- **WebSocket endpoints**:
  - `/ws/chat/{session_id}` — Streaming chat with full agent/tool execution
  - `/ws/events` — Server-sent events for real-time status updates
  - `/ws/logs` — Live log streaming
- **Cron scheduler** — Schedule bash commands or AI queries with cron expressions or
  plain intervals (`"every 5m"`, `"every 1h"`). Configurable tool approval mode.
- **Webhook triggers** — Named HTTP routes that fire AI agent actions. Supports HMAC-SHA256
  signature verification and `{body.x.y}` / `{headers.x}` template placeholders.
- **Budget enforcement** — In-memory daily/weekly/monthly cost limits with sub-millisecond
  enforcement. Synced to SQLite at configurable intervals.
- **Authentication** — Bearer token (`Authorization: Bearer <key>`) or `X-InkArms-Key` header.
  Localhost trusted by default (`trust_localhost: true`). IP-based rate limiting with lockout.
- **OpenAI-compatible proxy** — `/v1/chat/completions` for drop-in use with Continue.dev,
  Open WebUI, or any OpenAI-compatible client.
- **Auto-start platforms** — Hub starts all enabled platform adapters on launch; they restart
  automatically on crash.
- **SQLite persistence** (`~/.inkarms/hub.db`) — Budget history, cron job state, audit events.

#### Reasoning Context Support
- **`reasoning_content` field** — Agent client, session manager, and platform adapters all
  carry `reasoning_content` alongside `content` for thinking-capable models (e.g.
  `claude-3-7-sonnet`, `deepseek-r1`).
- **`normalize_reasoning_content()`** — Handles Anthropic `thinking` blocks and OpenAI
  `reasoning_content` fields uniformly.
- **Streaming preservation** — Reasoning content is accumulated during streaming and included
  in the final message object.
- **Platform and UI display** — Telegram, Slack, Discord, and the Rich TUI all surface
  reasoning content when present.

#### Web Search Tool
- **`BraveSearchTool`** — Integrates with the Brave Search API. API key stored encrypted
  via SecretsManager. Configured in the wizard under Tools → Web Search.

#### Rich TUI
- **`inkarms` launches the interactive UI directly** (no subcommand required).
- **Chat view** — Streaming responses, full Markdown rendering, syntax-highlighted code blocks,
  timestamps, tool execution panels (green/red/yellow borders by status).
- **Agent mode** — Real-time status line ("Running execute_bash..."), inline tool approval
  prompts (`a` allow, `d` deny, `A` allow all for session).
- **Dashboard view** — Session stats, provider status, recent sessions.
- **Sessions view** — Create, switch, and manage named conversation sessions.
- **Session persistence** — Active session restored on restart.
- **Slash commands** with tab completion: `/help`, `/model`, `/agent`, `/tools`, `/compact`,
  `/clear`, `/usage`, `/status`, `/save`, `/load`, `/history`, `/config`, `/menu`, `/quit`.
- **Config wizard accessible from chat** via `/config` slash command.
- **Status bar** — Provider, model, token count, cost, tools summary.

#### Configuration System
- **Hierarchical loading** — Global (`~/.inkarms/config.yaml`) → Profile → Project
  (`.inkarms/project.yaml`) → Environment variables (`INKARMS_*`).
- **Deep merge with `+`/`-` list operators** — Append or remove items in arrays without
  replacing the whole list.
- **`ProviderConfig.auto_discover_models`** — Enable/disable background model discovery
  (default: `false`).
- **`providers.yaml` defaults** — Bundled model catalogue for Anthropic, OpenAI, Gemini,
  GitHub Copilot, Ollama. User overrides merged from `~/.inkarms/providers.yaml`.
- **`ProvidersProxy`** — Lazy-loading dict proxy; provider data loaded on first access.
- **`clear_providers_cache()`** — Invalidates the in-process provider cache for hot reload.

#### Security
- **Structured blacklist** (`BlacklistConfig`) — Organised by category: single-word commands,
  multi-word patterns, sensitive paths, dangerous redirects, container patterns,
  command substitutions, DoS patterns, pipe-to-interpreters.
- **Bundled defaults** (`config/defaults/security.yaml`) — Opinionated safe defaults loaded
  at startup.
- **Audit logger buffer** — Configurable `buffer_size` and `flush_interval_seconds`.
  Events flushed to disk on a background thread.

#### Provider Layer
- **LiteLLM integration** — 100+ models across Anthropic, OpenAI, Google, Ollama,
  OpenRouter, GitHub Copilot, and others.
- **Fallback chains** — Automatic failover to the next provider on error.
- **Model aliases** — Short names (`fast`, `local`, etc.) resolved at request time.
- **Cost tracking** — Per-session and cumulative cost visible in the status bar and `/usage`.
- **Encrypted secrets** — Fernet encryption; keys stored in `~/.inkarms/secrets/`.
- **GitHub Copilot** — OAuth device-flow authentication; model catalogue includes GPT-4o,
  Claude 4.x, Gemini 2.x, and Grok 3.

#### Memory & Context
- **Session management** — Conversation history with token tracking via tiktoken.
- **Compaction strategies** — `summarize` (AI-generated summary), `truncate`, `sliding_window`.
  Auto-triggered at configurable context fill threshold (default 70%).
- **Handoff system** — Saves state to `HANDOFF.md` at 85% fill for clean session handoff.
- **Storage** — Daily logs, named snapshots, handoff documents under `~/.inkarms/memory/`.
- **Session chains** — Group channels (e.g. `cli` + `telegram`) to share a session.

#### Skills
- **Skill package format** — `SKILL.md` (instructions) + `skill.yaml` (metadata, keywords,
  permissions) in a named directory.
- **Skill discovery** — Keyword-indexed auto-discovery via `--auto-skill`. Explicit load via
  `--skill <name>`.
- **Global and project-local skills** — `~/.inkarms/skills/` overridden by `.inkarms/skills/`.
- **CLI** — `inkarms skill list/show/create/validate/install/remove/search/reindex`.

#### Tools & Agent Loop
- **Built-in tools** — `execute_bash` (sandboxed), `read_file`, `write_file`, `list_files`,
  `search_files`, `http_request`, `python_eval` (RestrictedPython), `git_operations`,
  `brave_search`.
- **Agent loop** — Iterates: call LLM → parse tool calls → execute → feed results back.
  Configurable max iterations and per-iteration timeout.
- **Approval modes** — `auto` (all tools run), `manual` (dangerous tools need confirmation),
  `disabled` (no tools).
- **Parallel tool execution** — Multiple tool calls in a single LLM turn run concurrently
  via `asyncio.gather()`.

#### Platforms
- **Telegram** adapter — Long polling. Supports `allowed_users`, HTML and MarkdownV2 parse
  modes, long-message splitting at sentence boundaries.
- **Slack** adapter — Socket Mode (persistent WebSocket; no public URL required).
- **Discord** adapter — Gateway WebSocket connection.
- **Platform-agnostic command registry** — Slash commands (`/help`, `/model`, `/usage`,
  `/status`, `/models`, `/clear`, `/compact`, `/tools`) shared by all platform adapters.
- **Rate limiting** — Token bucket per user, configurable messages-per-minute.
- **Session mapper** — Maps `(platform, user_id)` to session IDs for conversation continuity.

### Removed
- **`inkarms audit` CLI command** — Removed (unimplemented placeholder).
- **`inkarms profile` CLI command** — Removed (unimplemented placeholder).
- **`inkarms status` CLI command** — Removed (unimplemented placeholder).
- **`inkarms chat` CLI command** — Removed; `inkarms` (no subcommand) now launches the UI.
- **Textual backend** — Removed. Rich + prompt_toolkit is the only supported UI backend.
- **`DeepThinkingConfig`, `TaskRoutingConfig`** — Removed dead config classes.
- **`--task` and `--deep` CLI flags** — Removed (were print-only stubs).

---

## [0.1.0] - 2026-02-07

### Added
- Initial project structure with Typer-based CLI skeleton
- Command groups: `run`, `config`, `skill`, `memory`, `hub`, `platforms`, `tools`, `status`
- pyproject.toml with full dependency specification and optional extras (`[platforms]`, `[hub]`, `[all]`)
- Development tooling: ruff, mypy, pytest, pre-commit hooks
- Documentation structure: User Guide, Configuration Reference, CLI Reference, Security Guide,
  Skill Authoring Guide, Hub Guide, Platform Setup Guide
- Python 3.11+ required

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| Unreleased | — | Model discovery flag, audit fixes, updater improvements |
| 0.11.0 | 2026-02-24 | Hub daemon, reasoning support, wizard engine refactor, model discovery |
| 0.1.0 | 2026-02-07 | Initial project setup |

---

*"Every journey begins with a single tentacle movement."* 🐙
