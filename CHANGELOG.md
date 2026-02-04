# Changelog

All notable changes to InkArms will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.11.0] - Phase 1 Complete 🎉

### Added
- Initial project structure and CLI skeleton
- Typer-based CLI with all command groups
- Basic command structure for: run, config, skill, memory, status, audit, profile
- Development tooling: ruff, mypy, pytest, pre-commit
- Comprehensive documentation structure
- **Configuration System (Milestone 1.2)**:
  - Complete Pydantic configuration schema with validation
  - Hierarchical configuration loading (global → profile → project → env)
  - Deep merge with +/- array operations for list modification
  - Environment variable overrides (INKARMS_* pattern)
  - First-run setup (`inkarms config init`)
  - Project configuration (`inkarms config init --project`)
  - Profile creation (`inkarms config init --profile NAME`)
  - Working CLI commands: show, set, edit, validate, init
  - Configuration source tracking (`inkarms config show --sources`)
- **Provider Layer (Milestone 1.3)**:
  - LiteLLM integration for 100+ model support
  - Multi-provider support (OpenAI, Anthropic, Google, Ollama, etc.)
  - Automatic fallback chains with error classification
  - Model name resolution (aliases, defaults)
  - Encrypted secrets management (Fernet encryption)
  - Cost tracking per session and model
  - Provider health checking (`inkarms status health`)
  - Working `inkarms run` command with streaming support
  - Secrets CLI commands: set-secret, list-secrets, delete-secret
- **Skills System (Milestone 1.4)**:
  - Skill package format (SKILL.md + skill.yaml)
  - Skill parsing with YAML frontmatter support
  - Skill loading from global (~/.inkarms/skills/) and project (.inkarms/skills/) directories
  - Keyword-based skill discovery index
  - SkillManager for skill lifecycle management
  - CLI commands: list, show, create, validate, install, remove, search, reindex
  - Skill injection into system prompt via `--skill` flag
  - Auto-skill discovery via `--auto-skill` flag
  - 41 skill tests
- **Context & Memory System (Milestone 1.5)**:
  - Session management with conversation history
  - Token counting with tiktoken (context window tracking)
  - Context usage monitoring with thresholds
  - Compaction strategies: summarize, truncate, sliding_window
  - Handoff system for session continuity
  - Memory storage: daily logs, snapshots, handoffs
  - Session manager with auto-save
  - CLI commands: list, show, snapshot, compact, handoff, recover, status, clear
  - Context tracking integrated into `inkarms run`
  - `--no-memory` and `--new-session` flags
  - 40 memory tests
- **Security & Sandbox (Milestone 1.6)**:
  - Command filtering with whitelist/blacklist support
  - Multiple sandbox modes: whitelist, blacklist, prompt, disabled
  - Path restrictions to block access to sensitive directories
  - Safe command execution with timeout support
  - Audit logging with JSON Lines format
  - Event types: command execution, queries, config changes, skills, sessions
  - Log rotation and compression support
  - Privacy features: query hashing, response filtering, path redaction
  - Configurable buffering and flush intervals
  - Integration with security configuration
  - 46 security and audit tests
  - 219 total passing tests
- **Multi-Platform Messaging (Milestone 1.8)** - COMPLETE ✅:
  - Platform adapter protocol with abstract interface
  - Message router for concurrent multi-platform handling
  - Platform-agnostic message processor
  - Session mapper for (platform, user_id) → session_id mapping
  - Token bucket rate limiter for abuse prevention
  - Extended configuration schema with platform-specific settings
  - **Telegram bot adapter** (long polling mode)
  - **Slack adapter** (Socket Mode)
  - **Discord adapter** (Gateway WebSocket)
  - Platform connection modes: polling/WebSocket (no static IP required)
  - Optional dependencies: python-telegram-bot, slack-sdk, discord.py
  - Platform management CLI commands: start, stop, status
  - 150+ platform tests
  - ~370 total passing tests
- **Tool Use & Agent Loop (Milestone 1.9)** - COMPLETE ✅:
  - Tool registry and abstract Tool base class
  - JSON schema generation for tool definitions
  - 5 built-in tools: execute_bash, read_file, write_file, list_files, search_files
  - Agent loop with iterative execution (AI → parse → execute → feedback)
  - Tool call parser for Anthropic format
  - Approval system: AUTO, MANUAL, DISABLED modes
  - Tool filtering via whitelist/blacklist
  - Integration with security sandbox (all tools execute through sandbox)
  - Provider integration with tool use API support
  - Extended configuration schema with agent settings
  - CLI integration: `--tools` flag and `--tool-approval` mode
  - Tool management commands: list, info, test
  - 123 new tests (91 tool tests, 32 agent tests)
  - 440 total passing tests
- **Advanced Tool Use (Milestone 1.10)** - COMPLETE ✅:
  - Platform integration with streaming tool execution updates
  - HTTP request tool (GET/POST/PUT/DELETE with auth)
  - Python eval tool (safe code execution with RestrictedPython)
  - Git operations tool (status, commit, diff, log)
  - Streaming support with real-time execution events
  - Parallel tool execution using asyncio.gather()
  - Tool metrics tracking (usage, execution time, success rates)
- **TUI v1 (Milestone 1.7)** - COMPLETE ✅:
  - Interactive chat interface with streaming responses
  - Message display with Markdown rendering
  - Tool execution indicators
  - Session tracking (tokens, cost)
  - Configuration wizard (QuickStart and Advanced modes)
  - QuickStart wizard: Provider, API key, Security, Tools
  - Advanced wizard: 8 comprehensive sections
  - GitHub Copilot provider integration with OAuth device flow
  - `inkarms chat` command for TUI chat
  - `inkarms config init` for TUI configuration wizard

### Changed
- Configuration schema updated to include platforms section
- pyproject.toml updated with [platforms] optional dependencies
- Version updated to 0.11.0 for Phase 1 completion
- All Phase 1 milestones complete (1.1 through 1.10)
- TUI configuration wizard with QuickStart and Advanced modes
- GitHub Copilot added as provider option (GPT-5.2, Claude 4.5, Gemini 2.5, Grok 3)

### Deprecated
- Nothing yet!

### Removed
- Nothing yet!

### Fixed
- Nothing yet!

### Security
- Nothing yet!

---

## [0.1.0]

### Added
- 🐙 InkArms is born!
- Project structure following design specifications
- CLI skeleton with Typer
- Command groups: run, config, skill, memory, status, audit, profile
- Placeholder implementations for all commands
- pyproject.toml with full dependency specification
- Development tooling configuration (ruff, mypy, pytest)
- Pre-commit hooks
- Test infrastructure with pytest fixtures
- Documentation:
  - README.md with project philosophy
  - User Guide
  - Configuration Reference
  - Skill Authoring Guide
  - CLI Reference
  - Contributing Guide

### Technical Details
- Python 3.11+ required
- Dependencies: typer, textual, litellm, pydantic, pyyaml, rich, httpx, tiktoken, cryptography
- Package installable via `pip install -e .`
- Entry point: `inkarms` command

---

## Version History

| Version | Date | Milestone |
|---------|--|-----------|
| 0.1.0 |  | Project Setup (Phase 1, Milestone 1.1) |
| 0.2.0 |  | Configuration System (Phase 1, Milestone 1.2) |
| 0.3.0 |  | Provider Layer (Phase 1, Milestone 1.3) |
| 0.4.0 |  | Basic Skills (Phase 1, Milestone 1.4) |
| 0.5.0 |  | Context & Memory (Phase 1, Milestone 1.5) |
| 0.6.0 |  | Security & Sandbox (Phase 1, Milestone 1.6) |
| 0.7.0 |  | TUI v1 (Phase 1, Milestone 1.7) ✅ |
| 0.8.0 |  | Multi-Platform Adapters (Phase 1, Milestone 1.8) ✅ |
| 0.9.0 |  | Tool Use & Agent Loop (Phase 1, Milestone 1.9) ✅ |
| 0.10.0 |  | Advanced Tool Use (Phase 1, Milestone 1.10) ✅ |
| 0.11.0 |  | **Phase 1 Complete** - TUI Enhancements + GitHub Copilot ✅ |

---

*"Every journey begins with a single tentacle movement."* 🐙
