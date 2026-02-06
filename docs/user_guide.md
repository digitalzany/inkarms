# User Guide

Welcome, fellow tentacle enthusiast! This guide will help you get InkArms wrapped around your development workflow in no time.

## Table of Contents

- [Installation](#installation)
- [First Steps](#first-steps)
- [Basic Usage](#basic-usage)
- [Interactive Chat](#interactive-chat)
- [Understanding the CLI](#understanding-the-cli)
- [Working with Skills](#working-with-skills)
- [Memory & Context](#memory--context)
- [Multi-Platform Messaging](#multi-platform-messaging)
- [Tips & Tricks](#tips--tricks)

## Installation

### Requirements

- Python 3.11 or higher (we're modern octopi)
- A terminal that supports colors (because life is too short for monochrome)
- At least one AI provider API key (Anthropic, OpenAI, etc.)

### From PyPI (Recommended)
# Pip install will be available upon PyPI release.

### From Source (For the Adventurous)

```bash
# Clone the repository
git clone https://github.com/digitalzany/inkarms.git
cd inkarms

# Create a virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with development dependencies
pip install -e ".[dev]"
```

### Verify Installation

```bash
inkarms --version
# Output: inkarms version 0.1.0

inkarms --help
# Shows all available commands
```

If you see the version number, congratulations! You've successfully adopted an octopus. 🐙

## First Steps

### 1. Set Up Your API Keys

InkArms needs at least one AI provider to work its magic:

```bash
# Option A: Set environment variable (great for development)
export ANTHROPIC_API_KEY="your-api-key-here"

# Option B: Use the secure secrets manager (encrypted storage)
inkarms config set-secret anthropic
# You'll be prompted to enter your key securely

# List your configured secrets
inkarms config list-secrets
```

### 2. Initialize InkArms

Run the interactive configuration wizard:

```bash
# Open the interactive configuration wizard (recommended)
inkarms config init
```

The wizard offers two modes:
- **QuickStart** (2 minutes) — Essential settings: provider, API key, security, tools
- **Advanced** (10-15 minutes) — Full configuration with 8 detailed sections

Alternatively, use the CLI inline wizard:

```bash
# CLI mode (for terminals without interactive UI support)
inkarms config init --quick
```

This creates:
- `~/.inkarms/config.yaml` — Your global configuration
- `~/.inkarms/profiles/` — Named configuration presets
- `~/.inkarms/skills/` — Installed skills
- `~/.inkarms/memory/` — Session logs and handoffs
- `~/.inkarms/secrets/` — Encrypted API keys (restricted permissions)
- `~/.inkarms/cache/` — Temporary files

### 3. Verify Your Configuration

```bash
# Show current configuration
inkarms config show

# Show specific section
inkarms config show providers

# Validate everything is correct
inkarms config validate
```

### 4. Customize Your Config (Optional)

Edit the config directly or use the CLI:

```bash
# Open in your editor
inkarms config edit

# Or set values directly
inkarms config set providers.default "anthropic/claude-opus-4-20250514"
```

### 5. Your First Query

```bash
inkarms run "Hello! Tell me a fun fact about octopi."
```

If you see a response, you're ready to roll! 🎉

### 6. Start the Interactive UI

For a full interactive experience, launch InkArms with no arguments:

```bash
inkarms
```

This opens the main menu where you can navigate to:
- **Chat** — Conversational AI interface with streaming responses
- **Dashboard** — Session stats and provider status
- **Sessions** — Manage conversation sessions
- **Config** — Run the configuration wizard
- **Settings** — Adjust settings

Features in chat:
- **Streaming responses** — See AI responses as they're generated
- **Tool execution** — Watch tools run in real-time
- **Session tracking** — Token usage and costs displayed
- **Markdown rendering** — Rich formatted output
- **Slash commands** — Type `/help` for available commands

See [UI Guide](tui_guide.md) for complete documentation.

## Basic Usage

### Running Queries

The most common operation is `inkarms run`:

```bash
# Simple query (streaming by default)
inkarms run "Explain recursion with a food analogy"

# Specify a model (using alias or full name)
inkarms run --model fast "Write a haiku about debugging"
inkarms run --model openai/gpt-4 "Write a haiku about debugging"

# Include a file in context
inkarms run --context ./myfile.py "Explain this code"

# Preview without executing
inkarms run --dry-run "Test query"

# Adjust temperature (0.0-2.0)
inkarms run --temperature 0.9 "Be creative!"
```

### Coming Soon

```bash
# Use a specific task type (not yet implemented)
inkarms run "Review this code for bugs" --task coding

# Enable deep thinking for complex tasks (not yet implemented)
inkarms run "Design a microservices architecture" --deep
```

### Output Options

```bash
# Stream output (default)
inkarms run "Tell me a story"

# Wait for complete response
inkarms run "Generate a JSON schema" --no-stream

# Output as JSON (great for scripting)
inkarms run "List 5 Python libraries" --json

# Save to file
inkarms run "Write documentation" --output docs.md
```

## Understanding the CLI

InkArms is organized into command groups, each representing a different "arm":

```
inkarms              # Launch interactive UI (default, no subcommand)
├── run              # Execute AI queries (the main arm)
├── ui               # Launch UI with explicit backend selection
├── config           # Configuration management
├── skill            # Skill management
├── tools            # Tool management
├── memory           # Memory and context
├── status           # Health and monitoring
├── audit            # Audit logs
├── profile          # Profile management
└── platforms        # Platform messaging (Telegram, Slack, Discord)
```

### Global Options

These work with any command:

| Option | Short | Description |
|--------|-------|-------------|
| `--version` | `-V` | Show version |
| `--verbose` | `-v` | Verbose output |
| `--quiet` | `-q` | Minimal output |
| `--profile` | `-p` | Use specific profile |
| `--ui` | | UI backend (auto, rich, textual) |
| `--no-color` | | Disable colors |
| `--help` | `-h` | Show help |

### Getting Help

```bash
# General help
inkarms --help

# Command-specific help
inkarms run --help
inkarms config --help
inkarms skill install --help
```

## Working with Skills

Skills are InkArms' secret sauce — portable instructions that teach it specialized tasks.

### Listing Skills

```bash
inkarms skill list
inkarms skill list --verbose  # More details
```

### Installing Skills

```bash
# From GitHub
inkarms skill install github:user/repo/skill-name

# From a URL
inkarms skill install https://github.com/user/skills-repo

# From a local directory
inkarms skill install ./my-local-skill
```

### Using Skills

```bash
# Explicitly load a skill
inkarms run "Scan for vulnerabilities" --skill security-scan

# Skills are also auto-loaded based on your query!
# InkArms uses a smart index to find relevant skills
inkarms run "Check this Python code for security issues"
# ^ This might auto-load a security skill based on keywords
```

### Creating Skills

```bash
# Create a new skill from template
inkarms skill create my-awesome-skill

# This creates:
# ~/.inkarms/skills/my-awesome-skill/
# ├── SKILL.md      # Instructions for the AI
# └── skill.yaml    # Metadata and permissions
```

See [Skill Authoring](skill_authoring.md) for the full guide.

## Memory & Context

InkArms has excellent memory — it remembers your sessions and can pick up where you left off.

### Session Tracking

Every conversation is automatically tracked. You can check your session status:

```bash
# Check current session status
inkarms memory status

# Output shows:
#   Session ID, turns, tokens, cost, context usage %
#   Recommendations for compaction or handoff
```

### Viewing Memory

```bash
# List all memory files
inkarms memory list

# Filter by type
inkarms memory list --type daily     # Daily conversation logs
inkarms memory list --type snapshot  # Named snapshots
inkarms memory list --type handoff   # Handoff documents

# Show a specific day's log
inkarms memory show 2026-02-02

# View a named snapshot
inkarms memory show api-design
```

### Creating Snapshots

```bash
# Save current context as a named snapshot
inkarms memory snapshot "authentication-flow"

# With a description and topic
inkarms memory snapshot "auth-v2" --description "OAuth discussion" --topic "auth"
```

### Context Management

InkArms tracks token usage and warns you when context is getting full:

```bash
# Check context usage
inkarms memory status
# Shows: "Context: 50,000/128,000 (39.1%)"

# When context reaches 70%, InkArms recommends compaction
# When it reaches 85%, it recommends creating a handoff
```

When your conversation gets long, compact it:

```bash
# Compact using default strategy (from config)
inkarms memory compact

# Choose a strategy explicitly
inkarms memory compact --strategy summarize      # AI summarizes old messages (best)
inkarms memory compact --strategy truncate       # Remove old messages
inkarms memory compact --strategy sliding_window # Keep last N turns

# Dry run to see what would happen
inkarms memory compact --dry-run
```

### Handoffs

When you're about to hit context limits, create a handoff:

```bash
# Check if handoff is needed
inkarms memory handoff --check

# Create a handoff document
inkarms memory handoff

# Force creation even if below threshold
inkarms memory handoff --force

# Start fresh and recover from handoff
inkarms memory recover

# Keep the handoff file (don't archive)
inkarms memory recover --no-archive
```

### Memory Control in Run Command

```bash
# Don't track this query in memory
inkarms run "One-off question" --no-memory

# Start a completely fresh session
inkarms run "New topic" --new-session

# Re-run the last query with different settings
inkarms run rerun --model claude-opus
```

### Cleaning Up

```bash
# Clear current session
inkarms memory clear

# Delete a specific memory entry
inkarms memory delete 2026-02-02

# Delete old entries (not yet implemented)
# inkarms memory delete --older-than 30d
```

## Multi-Platform Messaging

InkArms can run on multiple messaging platforms, allowing you to interact with your AI assistant from Telegram, Slack, Discord, and more - all without needing a webhook server or public IP address!

### Supported Platforms

- **Telegram** - Bot API with long polling
- **Slack** - Socket Mode (WebSocket)
- **Discord** - Gateway WebSocket connection
- More platforms coming soon (WhatsApp, iMessage, Signal, Teams, WeChat)

### Quick Start

1. **Install platform dependencies:**
   ```bash
   pip install -e ".[platforms]"
   ```

2. **Set up your bot** (see [Platform Setup Guide](platforms.md) for detailed instructions):
   - Telegram: Create bot with @BotFather
   - Slack: Create app at api.slack.com
   - Discord: Create app at discord.com/developers

3. **Configure InkArms:**
   ```yaml
   # ~/.inkarms/config.yaml
   platforms:
     enable: true

     telegram:
       enable: true
       bot_token: "${TELEGRAM_BOT_TOKEN}"

     slack:
       enable: true
       bot_token: "${SLACK_BOT_TOKEN}"
       app_token: "${SLACK_APP_TOKEN}"

     discord:
       enable: true
       bot_token: "${DISCORD_BOT_TOKEN}"
   ```

4. **Start your bots:**
   ```bash
   # Start all enabled platforms
   inkarms platforms start

   # Or start specific platform
   inkarms platforms start --platform telegram
   ```

5. **Chat with your bot** on your favorite platform!

### Platform Commands

```bash
# List available platforms and their status
inkarms platforms list

# Start all enabled platforms
inkarms platforms start

# Start specific platform
inkarms platforms start --platform telegram
inkarms platforms start --platform slack
inkarms platforms start --platform discord

# Check platform configuration status
inkarms platforms status

# Stop platforms (Ctrl+C in running terminal)
```

### Platform Features

All platforms support:
- ✅ **Streaming responses** - Messages update in real-time
- ✅ **Markdown formatting** - Rich text with code blocks
- ✅ **Rate limiting** - Prevents spam (10 messages/minute default)
- ✅ **User whitelisting** - Restrict access to specific users
- ✅ **Session persistence** - Maintains conversation context
- ✅ **Security sandbox** - Safe command execution (future)

### Example Configuration

```yaml
platforms:
  enable: true

  # Global settings
  rate_limit_per_user: 10  # Messages per minute
  max_concurrent_sessions: 100

  telegram:
    enable: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    mode: polling
    parse_mode: "MarkdownV2"
    # Optional: restrict to specific users
    allowed_users: ["123456789"]

  slack:
    enable: true
    bot_token: "${SLACK_BOT_TOKEN}"
    app_token: "${SLACK_APP_TOKEN}"
    mode: socket
    # Optional: restrict to specific channels
    allowed_channels: ["C0123456"]

  discord:
    enable: true
    bot_token: "${DISCORD_BOT_TOKEN}"
    mode: gateway
    command_prefix: "!"
    # Optional: restrict to specific servers
    allowed_guilds: ["987654321"]
```

### Security Best Practices

1. **Use environment variables** for tokens (never hardcode)
2. **Enable user/channel whitelists** for production bots
3. **Monitor audit logs** to see who's using your bot
4. **Set appropriate rate limits** to prevent abuse

For detailed setup instructions for each platform, see the [Platform Setup Guide](platforms.md).

## Tips & Tricks

### Shell Aliases

Add these to your `.bashrc` or `.zshrc`:

```bash
alias ia="inkarms run"
alias iad="inkarms run --deep"
alias ias="inkarms status"

# Quick coding help
function iacode() {
    inkarms run "$1" --task coding --model claude-opus
}
```

### Piping Content

```bash
# Pipe file content
cat mycode.py | inkarms run "Review this code"

# Pipe command output
git diff | inkarms run "Summarize these changes"

# Save output
inkarms run "Generate unit tests" > tests.py
```

### Using Profiles

Create profiles for different contexts:

```bash
# Create a development profile
inkarms profile create dev

# Edit it
inkarms profile edit dev

# Switch to it
inkarms profile use dev

# Use temporarily
inkarms run "Query" --profile dev
```

### Project-Specific Config

Create `.inkarms/project.yaml` in your project root:

```yaml
# .inkarms/project.yaml
providers:
  default: "anthropic/claude-opus-4-20250514"  # Use the best for this project

security:
  +whitelist:  # Add to global whitelist
    - npm
    - docker
```

## Troubleshooting

### "API key not found"

```bash
# Check if it's set
echo $ANTHROPIC_API_KEY

# Or use the secrets manager
inkarms config list-secrets
inkarms config set-secret anthropic
```

### "Command blocked"

Your sandbox is working! Either:
1. Add the command to your whitelist
2. Use `--approve` to manually approve commands
3. Check `inkarms config show security.whitelist`

### "Context limit reached"

```bash
# Compact your context
inkarms memory compact

# Or create a handoff and start fresh
inkarms memory handoff
```

### Getting More Help

```bash
# Check provider health
inkarms status health

# View recent audit logs
inkarms audit tail

# Join our Discord for community support
# https://discord.gg/inkarms
```

---

## Next Steps

- [Configuration Reference](configuration.md) — Master all the settings
- [Skill Authoring](skill_authoring.md) — Create your own skills
- [CLI Reference](cli_reference.md) — Every command documented

---

*"An octopus never stops learning. Neither should you."* 🐙
