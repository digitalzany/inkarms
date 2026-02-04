# CLI Reference

The complete reference for every InkArms command. Each arm, fully documented.

## Global Options

These options work with any command:

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-V` | Show version and exit |
| `--verbose` | `-v` | Enable verbose output |
| `--quiet` | `-q` | Minimal output |
| `--profile` | `-p` | Use specific config profile |
| `--no-color` | | Disable colored output |
| `--help` | `-h` | Show help message |

## Command Overview

```
inkarms
├── run          # Execute AI queries
├── chat         # Interactive TUI chat interface
├── config       # Configuration management
├── skill        # Skill management
├── tools        # Tool management
├── memory       # Memory and context
├── status       # Health and monitoring
├── audit        # Audit logs
├── profile      # Profile management
├── platforms    # Platform messaging
└── interactive  # REPL mode (coming soon)
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
| `--task` | `-t` | TEXT | auto | Task type (not yet implemented) |
| `--skill` | `-s` | TEXT | auto | Explicitly load a skill (not yet implemented) |
| `--deep` | `-d` | FLAG | false | Enable deep thinking chain (not yet implemented) |
| `--approve` | `-a` | FLAG | false | Require approval for commands |
| `--stream/--no-stream` | | FLAG | stream | Stream response |
| `--yes` | `-y` | FLAG | false | Skip confirmations |
| `--dry-run` | | FLAG | false | Show what would happen |
| `--context` | | PATH | | Include file in context |
| `--output` | `-o` | PATH | | Write response to file |
| `--json` | | FLAG | false | Output as JSON |
| `--temperature` | | FLOAT | 0.7 | Sampling temperature (0.0-2.0) |
| `--max-tokens` | | INT | | Maximum tokens in response |

### Examples

```bash
# Simple query (streaming by default)
inkarms run "Explain quantum computing"

# With specific model (alias or full name)
inkarms run --model fast "Write a haiku"
inkarms run --model openai/gpt-4 "Write a haiku"

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
| `--task` | `-t` | Override task type |
| `--deep` | `-d` | Enable deep thinking |

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
| `--quick` | `-q` | CLI inline wizard (instead of TUI) |
| `--force` | `-f` | Force overwrite (only valid with `--quick`) |

#### Wizard Modes

**TUI Mode (Default):**
Opens a beautiful terminal wizard with two options:
- **QuickStart** (2 minutes) - Essential settings only
- **Advanced** (10-15 minutes) - Full 8-section configuration

**CLI Mode (`--quick`):**
Inline command-line prompts using questionary.

#### Examples

```bash
# Open TUI wizard (recommended)
inkarms config init

# CLI inline wizard
inkarms config init --quick

# CLI wizard with force overwrite (for automation)
inkarms config init --quick --force
```

#### What Gets Created

- `~/.inkarms/` directory structure
- `~/.inkarms/config.yaml` with your settings
- Encrypted API key storage (if provided)

See [TUI Guide](tui_guide.md) for wizard walkthrough.

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

Search for skills.

```bash
inkarms skill search QUERY [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `QUERY` | Search query |

| Option | Description |
|--------|-------------|
| `--remote` | Search remote registries |

### inkarms skill show

Show skill details.

```bash
inkarms skill show NAME
```

### inkarms skill install

Install a skill.

```bash
inkarms skill install SOURCE [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `SOURCE` | Skill source (github:user/repo/skill, URL, or path) |

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Overwrite existing |

#### Source Formats

```bash
# From GitHub
inkarms skill install github:user/repo/skill-name
inkarms skill install github:user/repo/skill-name@v1.0.0

# From URL
inkarms skill install https://github.com/user/repo

# From local path
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

### inkarms skill update

Update skill(s).

```bash
inkarms skill update [NAME]
```

| Argument | Description |
|----------|-------------|
| `NAME` | Skill name (updates all if omitted) |

### inkarms skill create

Create a new skill from template.

```bash
inkarms skill create NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--template` | Template to use |

### inkarms skill validate

Validate a skill.

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

### inkarms memory show

Show memory content.

```bash
inkarms memory show NAME
```

| Argument | Description |
|----------|-------------|
| `NAME` | Memory name or date |

### inkarms memory snapshot

Create a memory snapshot.

```bash
inkarms memory snapshot NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--topic` | Topic description |

### inkarms memory compact

Compact the current context.

```bash
inkarms memory compact [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--strategy` | summarize, truncate, sliding_window |
| `--keep-recent` | Turns to preserve |

### inkarms memory clean

Clean non-essential messages.

```bash
inkarms memory clean
```

### inkarms memory handoff

Create or check handoff document.

```bash
inkarms memory handoff [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--force` | `-f` | Force creation |
| `--check` | | Check without creating |

### inkarms memory recover

Recover from handoff.

```bash
inkarms memory recover [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--no-archive` | Don't archive handoff |

### inkarms memory delete

Delete memory files.

```bash
inkarms memory delete NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--older-than` | Duration (e.g., '30d') |

---

## inkarms status

Status and health monitoring.

```bash
inkarms status [COMMAND] [OPTIONS]
```

### Options (status overview)

| Option | Short | Description |
|--------|-------|-------------|
| `--watch` | `-w` | Live updates |
| `--interval` | | Update interval (seconds) |
| `--json` | | Output as JSON |

### inkarms status health

Check provider health.

```bash
inkarms status health [PROVIDER] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--all` | Check all providers |

### inkarms status tokens

Show token usage.

```bash
inkarms status tokens [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--today` | Today only |
| `--by-model` | Group by model |

### inkarms status cost

Show cost tracking.

```bash
inkarms status cost [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--month` | Monthly cost |
| `--by-model` | Group by model |

### inkarms status context

Show context window usage.

```bash
inkarms status context
```

---

## inkarms audit

Audit log access.

```bash
inkarms audit [COMMAND]
```

### inkarms audit tail

View recent events.

```bash
inkarms audit tail [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--lines` | `-n` | Number of lines |

### inkarms audit search

Search audit events.

```bash
inkarms audit search [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--type` | Event type |
| `--since` | Start time (e.g., '24h', '7d') |
| `--until` | End time |
| `--severity` | Minimum severity |
| `--session` | Session ID |
| `--contains` | Text search |

### inkarms audit stats

Show statistics.

```bash
inkarms audit stats METRIC [OPTIONS]
```

| Argument | Description |
|----------|-------------|
| `METRIC` | tokens, cost, requests |

| Option | Description |
|--------|-------------|
| `--today` | Today only |
| `--week` | Last 7 days |
| `--month` | Last 30 days |

### inkarms audit export

Export audit log.

```bash
inkarms audit export [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--format` | `-f` | json, jsonl, csv, markdown |
| `--output` | `-o` | Output file |
| `--since` | | Start time |
| `--type` | | Event type filter |
| `--session` | | Session filter |

---

## inkarms profile

Profile management.

```bash
inkarms profile [COMMAND]
```

### inkarms profile list

List all profiles.

```bash
inkarms profile list
```

### inkarms profile show

Show profile details.

```bash
inkarms profile show NAME
```

### inkarms profile create

Create a new profile.

```bash
inkarms profile create NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--from` | Copy from existing profile |

### inkarms profile use

Switch to a profile.

```bash
inkarms profile use NAME [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--default` | Set as default |

### inkarms profile edit

Edit a profile.

```bash
inkarms profile edit NAME
```

### inkarms profile delete

Delete a profile.

```bash
inkarms profile delete NAME [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--yes` | `-y` | Skip confirmation |

---

## inkarms chat

Launch the interactive TUI chat interface.

```bash
inkarms chat [OPTIONS]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--session` | `-s` | Session ID for conversation tracking (default: "default") |

### Examples

```bash
# Start chat with default session
inkarms chat

# Start chat with named session
inkarms chat --session my-project
inkarms chat -s project-alpha

# Different sessions maintain separate conversation history
inkarms chat -s work
inkarms chat -s personal
```

### Features

- **Streaming responses** - AI responses update incrementally
- **Tool execution indicators** - See when tools are running
- **Session tracking** - Token usage and cost displayed
- **Markdown rendering** - Rich text formatting
- **Keyboard shortcuts** - Q to quit, Enter to send

See [TUI Guide](tui_guide.md) for complete documentation.

---

## inkarms interactive

Start REPL mode for continuous interaction.

```bash
inkarms interactive [OPTIONS]
```

*Coming soon - use `inkarms chat` for interactive TUI*

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

# Or show completion script
inkarms --show-completion bash > inkarms-completion.bash
```

---

*"Eight arms, infinite possibilities."* 🐙
