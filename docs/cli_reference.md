# CLI Reference

The complete reference for every InkArms command. Each arm, fully documented.

## Global Options

These options work with any command:

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-V` | Show version and exit |
| `--profile` | `-p` | Use specific config profile |
| `--ui` | | UI backend selection (auto, rich) |
| `--no-color` | | Disable colored output |
| `--help` | `-h` | Show help message |

## Command Overview

```
inkarms              # Launch interactive UI (default, no subcommand)
├── run              # Execute AI queries
├── ui               # Launch UI with explicit backend selection
├── config           # Configuration management
├── skill            # Skill management
├── tools            # Tool management
├── memory           # Memory and context
├── status           # Health and monitoring
├── platforms        # Platform messaging
└── hub              # Hub daemon management
```

---

## inkarms run

Execute a query against the AI.

```bash
inkarms run [OPTIONS] [QUERY]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `QUERY` | The query to send to the AI |

### Options

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--model` | `-m` | TEXT | config | Model to use (name or alias) |
| `--skill` | `-s` | TEXT | | Explicitly load a skill by name or path |
| `--auto-skill/--no-auto-skill` | | FLAG | false | Auto-discover relevant skills based on query |
| `--approve` | `-a` | FLAG | false | Require approval for commands |
| `--stream/--no-stream` | | FLAG | stream | Stream response |
| `--yes` | `-y` | FLAG | false | Skip confirmations |
| `--dry-run` | | FLAG | false | Show what would happen |
| `--context` | | PATH | | Include file in context |
| `--output` | `-o` | PATH | | Write response to file |
| `--json` | | FLAG | false | Output as JSON |
| `--temperature` | | FLOAT | 0.7 | Sampling temperature (0.0-2.0) |
| `--max-tokens` | | INT | | Maximum tokens in response |
| `--tools/--no-tools` | | FLAG | false | Enable tool use (function calling) |
| `--tool-approval` | | TEXT | manual | Tool approval mode: auto, manual, or disabled |
| `--no-memory` | | FLAG | false | Don't track this query in session memory |
| `--new-session` | | FLAG | false | Start a fresh session |

### Examples

```bash
# Simple query (streaming by default)
inkarms run "Explain quantum computing"

# With specific model (alias or full name)
inkarms run --model fast "Write a haiku"
inkarms run --model openai/gpt-4 "Write a haiku"

# Enable tools and auto-approve
inkarms run "Check git status" --tools --tool-approval auto

# Auto-discover relevant skills
inkarms run "Review this code for security issues" --auto-skill

# Include context file
inkarms run --context ./main.py "Explain this code"

# Preview without executing
inkarms run --dry-run "Test query"

# Non-streaming with JSON output
inkarms run --no-stream --json "List 5 Python libraries"

# Output to file
inkarms run "Generate docs" --output README.md

# Non-interactive
inkarms run "Fix the bug" --yes --no-stream
```

### Subcommands

#### inkarms run rerun

Re-run the last query with different settings.

```bash
inkarms run rerun [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--model` | `-m` | Override model |

---

## inkarms config

Configuration management.

```bash
inkarms config [COMMAND]
```

### inkarms config show

Show configuration values.

```bash
inkarms config show [SECTION] [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `SECTION` | Config section (e.g., 'providers', 'security.whitelist') |

| Option | Description |
|--------|-------------|
| `--yaml` | Output as YAML |
| `--json` | Output as JSON |
| `--effective` | Show merged configuration (default) |
| `--sources` | Show configuration source files |
| `--profile` | Profile to use |

#### Examples

```bash
# Show all config (YAML format, default)
inkarms config show

# Show specific section
inkarms config show providers
inkarms config show security.whitelist

# Show as JSON
inkarms config show --json

# Show configuration sources
inkarms config show --sources
```

### inkarms config set

Set a configuration value.

```bash
inkarms config set KEY VALUE [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `KEY` | Config key (e.g., 'providers.default') |
| `VALUE` | Value to set |

| Option | Description |
|--------|-------------|
| `--scope` | Scope: global, profile, project |
| `--profile` | Profile name (if scope is 'profile') |

### inkarms config edit

Open configuration in editor.

```bash
inkarms config edit [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--profile` | Edit specific profile |
| `--project` | Edit project config |
| `--editor` | Editor to use |

### inkarms config set-secret

Set an API key secret.

```bash
inkarms config set-secret PROVIDER [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `PROVIDER` | Provider name (openai, anthropic, etc.) |

| Option | Description |
|--------|-------------|
| `--value` | API key (will prompt if not provided) |

### inkarms config list-secrets

List configured secrets.

```bash
inkarms config list-secrets
```

### inkarms config delete-secret

Delete a stored secret.

```bash
inkarms config delete-secret PROVIDER [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--yes` | `-y` | Skip confirmation |

### inkarms config validate

Validate configuration.

```bash
inkarms config validate [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--file` | Config file to validate |
| `--profile` | Profile to validate |

### inkarms config init

Initialize InkArms configuration with interactive wizard.

```bash
inkarms config init [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--project` | | Initialize project config in current directory |
| `--profile` | `-p` | Profile name to initialize |
| `--force` | `-f` | Force overwrite existing config |

#### Wizard Modes

**Interactive Mode (Default):**
Opens a terminal wizard with two options:
- **QuickStart** (2 minutes) - Essential settings only
- **Advanced** (10-15 minutes) - Full 8-section configuration

**CLI Mode (`--quick`):**
Inline command-line prompts.

#### Examples

```bash
# Open interactive wizard (recommended)
inkarms config init

# Initialize project config in current directory
inkarms config init --project

# Force reinitialize
inkarms config init --force
```

#### What Gets Created

- `~/.inkarms/` directory structure
- `~/.inkarms/config.yaml` with your settings
- Encrypted API key storage (if provided)

See [UI Guide](tui_guide.md) for wizard walkthrough.

---

## inkarms skill

Skill management.

```bash
inkarms skill [COMMAND]
```

### inkarms skill list

List installed skills.

```bash
inkarms skill list [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--verbose` | `-v` | Show detailed information |

### inkarms skill search

Search for skills by keyword.

```bash
inkarms skill search QUERY [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `QUERY` | Search query |

| Option | Description |
|--------|-------------|
| `--max` | Maximum number of results |

### inkarms skill show

Show skill details.

```bash
inkarms skill show NAME
```

### inkarms skill install

Install a skill from a local directory.

```bash
inkarms skill install SOURCE [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `SOURCE` | Path to skill directory |

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Overwrite existing |

```bash
# Install from local path
inkarms skill install ./my-skill
inkarms skill install /absolute/path/to/skill
```

### inkarms skill remove

Remove a skill.

```bash
inkarms skill remove NAME [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--yes` | `-y` | Skip confirmation |

### inkarms skill create

Create a new skill from template.

```bash
inkarms skill create NAME [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--description` | `-d` | Skill description |
| `--location` | `-l` | global or project (default: global) |

### inkarms skill validate

Validate a skill directory.

```bash
inkarms skill validate PATH
```

### inkarms skill reindex

Rebuild the skill index.

```bash
inkarms skill reindex
```

---

## inkarms memory

Memory and context management.

```bash
inkarms memory [COMMAND]
```

### inkarms memory list

List memory files.

```bash
inkarms memory list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--type` | Filter: daily, handoff, snapshot |
| `--limit` | Maximum results |

### inkarms memory show

Show memory content.

```bash
inkarms memory show NAME
```

| Argument | Description |
|----------|-------------|
| `NAME` | Memory name or date (e.g., `2026-02-02`, `my-snapshot`) |

### inkarms memory snapshot

Create a memory snapshot.

```bash
inkarms memory snapshot NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--description` | Snapshot description |
| `--topic` | Topic tag |

### inkarms memory compact

Compact the current context.

```bash
inkarms memory compact [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--strategy` | summarize, truncate, sliding_window |
| `--keep-recent` | Number of recent turns to preserve |
| `--dry-run` | Show what would happen without doing it |

### inkarms memory clean

Remove non-essential messages from context.

```bash
inkarms memory clean
```

### inkarms memory handoff

Create or check a handoff document.

```bash
inkarms memory handoff [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Force creation even if below threshold |
| `--check` | | Check if handoff is needed without creating |

### inkarms memory recover

Recover session from handoff document.

```bash
inkarms memory recover [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--no-archive` | Don't archive the handoff file after recovery |

### inkarms memory delete

Delete memory files.

```bash
inkarms memory delete NAME [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--yes` | `-y` | Skip confirmation |

### inkarms memory status

Show current session status.

```bash
inkarms memory status
```

### inkarms memory clear

Clear the current session.

```bash
inkarms memory clear [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--yes` | `-y` | Skip confirmation |

---

## inkarms status

Status and health monitoring.

```bash
inkarms status [COMMAND] [OPTIONS]
```

### inkarms status health

Check provider health.

```bash
inkarms status health [PROVIDER] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--all` | Check all providers |

---

## inkarms tools

Tool management and testing.

```bash
inkarms tools [COMMAND]
```

### inkarms tools list

List all available tools.

```bash
inkarms tools list [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--all` | `-a` | Include tools with missing optional dependencies |

### inkarms tools info

Show detailed tool information.

```bash
inkarms tools info TOOL_NAME
```

### inkarms tools test

Test a tool with given parameters.

```bash
inkarms tools test TOOL_NAME [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--params` | `-p` | Parameters as JSON string |

### inkarms tools metrics

Show tool usage statistics.

```bash
inkarms tools metrics [TOOL_NAME] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--clear` | Reset metrics |

---

## inkarms platforms

Start platform adapters (Telegram, Slack, Discord) as a foreground process. For production use, prefer running platforms through the Hub daemon (`inkarms hub start`), which adds crash recovery, hot-reload, and session persistence.

```bash
inkarms platforms list                          # Show configured platforms and status
inkarms platforms start                         # Start all enabled platforms (blocks)
inkarms platforms start --platform telegram     # Start a specific platform
inkarms platforms status                        # Check platform health
```

→ [Platform Setup Guide](platforms.md)

---

## inkarms hub

InkArms Hub daemon management.

```bash
inkarms hub [COMMAND]
```

### inkarms hub start

Start the Hub daemon.

```bash
inkarms hub start [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--background` | `-b` | Run as background daemon |

### inkarms hub stop

Gracefully stop the Hub daemon.

```bash
inkarms hub stop
```

### inkarms hub restart

Stop and restart the Hub daemon.

```bash
inkarms hub restart
```

### inkarms hub status

Show Hub status (uptime, model, today's cost).

```bash
inkarms hub status
```

### inkarms hub logs

View Hub log output.

```bash
inkarms hub logs [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--lines` | `-n` | Number of lines to show (default: 50) |
| `--follow` | `-f` | Follow log output (like `tail -f`) |

### inkarms hub install

Install Hub as a system service (auto-start at login).

```bash
inkarms hub install
```

Installs as launchd plist on macOS or systemd user service on Linux.

### inkarms hub uninstall

Remove the Hub system service.

```bash
inkarms hub uninstall
```

### inkarms hub key

Show or rotate the Hub API key.

```bash
inkarms hub key [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--rotate` | Generate and store a new API key |

### inkarms hub dev

Start Hub in development mode with auto-reload.

```bash
inkarms hub dev
```

---

## inkarms (no subcommand)

Launch the interactive UI. This is the default behavior when running `inkarms` without arguments.

```bash
inkarms [OPTIONS]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--ui` | | UI backend: auto, rich (default: auto) |
| `--profile` | `-p` | Use specific config profile |

### Examples

```bash
# Launch UI with default settings
inkarms

# Launch with explicit Rich backend
inkarms --ui rich
```

### Features

The UI provides these views (navigable via main menu or slash commands):
- **Menu** - Main navigation hub
- **Chat** - Conversational AI interface with streaming, markdown, and tool execution
- **Dashboard** - Session stats, provider status
- **Sessions** - Create, switch, and manage conversation sessions
- **Config** - Configuration wizard (QuickStart + Advanced)
- **Settings** - Quick settings adjustments

See [UI Guide](tui_guide.md) for complete documentation.

---

## inkarms ui

Explicitly launch the UI with backend selection.

```bash
inkarms ui [OPTIONS]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--backend` | `-b` | UI backend: auto, rich (default: auto) |

### Examples

```bash
# Launch with default backend (Rich)
inkarms ui

# Launch with Rich backend explicitly
inkarms ui --backend rich
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Authentication error |
| 4 | Provider error |
| 5 | Validation error |
| 10 | Command blocked (security) |
| 11 | User cancelled |
| 20 | Budget exceeded |

---

## Shell Completion

```bash
# Install completions
inkarms --install-completion bash
inkarms --install-completion zsh
inkarms --install-completion fish
```

---

*"Eight arms, infinite possibilities."* 🐙
