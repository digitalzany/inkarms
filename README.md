# 🐙 InkArms - AI Agent CLI Tool

<p align="center">
  <em>Think with your arms. Act with intent. Leave your mark.</em>
</p>

<p align="center">
  <picture>
    <img src="./docs/assets/logo.png" alt="InkArms Logo" width="200" />
  </picture>
</p>

<p align="center">
  <a href="https://github.com/digitalzany/inkarms/actions"><img src="https://img.shields.io/github/actions/workflow/status/digitalzany/inkarms/ci.yml?branch=main&style=for-the-badge" alt="Build Status"></a>
  <a href="https://github.com/digitalzany/inkarms/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
</p>

---

## What is InkArms?

**InkArms** is an AI Agent CLI tool inspired by the magnificent octopus — a creature that doesn't just think with its head, but with its *arms*.

Each arm of an octopus has its own mini-brain, capable of independent action while coordinating with the whole. InkArms brings this philosophy to AI agents:

- **Ink** represents memory, trace, and intent — every action leaves a mark
- **Arms** represent action, parallelism, and execution — multiple capabilities working in concert

> InkArms doesn't "chat" — it **acts**, **remembers**, and **leaves records**.

```
         ___
       /     \
      |   o o |
    /|\   ||   /|\
   / | \  ||  / | \
  |  |  | || |  |  |    "I have 8 arms and I'm not afraid to use them!"
  |  |  | || |  |  |
    /   | || |   \  
   /   /  ||  \   \
```

## Why InkArms?

Most AI tools are glorified chatbots. You ask, they answer, and poof — the conversation vanishes like ink in water.

InkArms is different:

- **Multi-Provider Support** — Anthropic, OpenAI, Google, Ollama, and more via LiteLLM
- **Multi-Platform Messaging** — Chat with your AI via Telegram, Slack, Discord, and more (no static IP required!)
- **Skills System** — Teach your AI new tricks with portable, shareable skill files
- **Deep Thinking** — Chain multiple models for thorough analysis
- **Smart Routing** — Automatically pick the best model for each task
- **Secure Sandbox** — Commands execute safely with whitelist protection
- **Persistent Memory** — Sessions are logged, handoffs are preserved
- **Beautiful TUI** — A terminal interface that sparks joy

## Quick Start

### Installation

```bash
# From PyPI (coming soon)
pip install inkarms

# With platform messaging support (Telegram, Slack, Discord, etc.)
pip install inkarms[platforms]

# From source (for the adventurous)
git clone https://github.com/digitalzany/inkarms.git
cd inkarms
pip install -e ".[dev]"

# From source with platforms
pip install -e ".[platforms,dev]"
```

### Your First Tentacle Wave

```bash
# Check if InkArms is ready to embrace you
inkarms --version

# See all the arms at your disposal
inkarms --help

# Initialize with interactive wizard
inkarms config init

# Ask InkArms to do something (requires API key setup)
inkarms run "Explain quantum computing like I'm a curious octopus"

# Launch the interactive chat interface
inkarms chat
```

### Configuration

InkArms looks for configuration in these places (in order of priority):

1. CLI flags (`--model`, `--profile`, etc.)
2. Environment variables (`INKARMS_*`)
3. Project config (`./.inkarms/project.yaml`)
4. Active profile (`~/.inkarms/profiles/<name>.yaml`)
5. Global config (`~/.inkarms/config.yaml`)

### Initialize InkArms

```bash
# Initialize InkArms (creates ~/.inkarms/ directory and config)
inkarms config init

# Or initialize with a project config
inkarms config init --project
```

### Set up your first API key:

```bash
# Option 1: Environment variable
export ANTHROPIC_API_KEY="your-key-here"

# Option 2: Encrypted secrets storage
inkarms config set-secret anthropic
# You'll be prompted to enter your key securely

# List configured secrets
inkarms config list-secrets
```

### View and validate configuration:

```bash
# Show current configuration
inkarms config show

# Show specific section
inkarms config show providers

# Validate configuration
inkarms config validate
```

Create a minimal config:

```yaml
# ~/.inkarms/config.yaml
providers:
  default: "anthropic/claude-sonnet-4-20250514"
  aliases:
    fast: "openai/gpt-3.5-turbo"
    smart: "anthropic/claude-opus-4-20250514"

security:
  sandbox:
    enable: true
    mode: whitelist
  whitelist:
    - ls
    - cat
    - git
    - python
```

## Features

### Skills System

Skills are portable instructions that teach InkArms specialized tasks:

```bash
# Install a skill from GitHub
inkarms skill install github:inkarms/skills/security-scan

# List your skills
inkarms skill list

# Use a skill explicitly
inkarms run "Review my code" --skill security-scan
```

### Tool Use & Agent Loop

InkArms can now **execute tools** to accomplish complex tasks autonomously:

```bash
# Enable tool use (manual approval by default)
inkarms run "List files in current directory" --tools

# Auto-approve all tools
inkarms run "Create hello.txt with 'Hello World'" --tools --tool-approval auto

# List available tools
inkarms tools list

# Test a tool
inkarms tools test read_file --params '{"path": "README.md"}'

# Show tool details
inkarms tools info execute_bash
```

**Built-in Tools:**
- **execute_bash** - Run shell commands through security sandbox
- **read_file** - Read text files with encoding support
- **write_file** - Create/overwrite files
- **list_files** - List directory contents recursively
- **search_files** - Glob and grep-like file search

**Agent Loop Features:**
- Iterative execution: AI → parse tools → execute → feed results → continue
- Approval modes: AUTO (all tools), MANUAL (dangerous need approval), DISABLED
- Tool filtering via whitelist/blacklist
- All tools execute through security sandbox
- Complete audit logging

**Advanced Tool Use:**
- **HTTP requests** - Make API calls with authentication
- **Python eval** - Safe code execution
- **Git operations** - Clone, status, diff, log commands
- **Streaming** - Real-time tool execution updates
- **Parallel execution** - Run independent tools concurrently
- **Tool metrics** - Track execution time, success rates

### Multi-Platform Messaging

Chat with InkArms through your favorite messaging platforms! **No static IP or webhook setup required** - everything uses polling or WebSocket modes that work seamlessly on your personal computer:

```bash
# Install platform support
pip install -e ".[platforms]"

# Configure your bots (one-time setup)
inkarms config set-secret telegram-bot-token
inkarms config set-secret slack-bot-token
inkarms config set-secret discord-bot-token

# Start all enabled platforms
inkarms platforms start

# Check platform status
inkarms platforms status
```

**Supported Platforms:**
- ✅ **Telegram** - Long polling (perfect for personal use)
- ✅ **Slack** - Socket Mode (works behind firewalls)
- ✅ **Discord** - Gateway WebSocket (standard bot connection)
- 📋 **iMessage** - macOS local monitoring (optional)
- 📋 **Signal** - via signal-cli (optional)
- 📋 **WhatsApp** - Personal use alternatives (optional)

**Key Benefits:**
- No static IP address needed
- No domain or SSL certificates required
- Works behind NAT/firewalls
- Each user gets isolated conversation sessions
- Rate limiting prevents abuse
- All security features apply (sandbox, audit logging)

See [Platform Setup Guide](docs/platforms.md) for detailed configuration per platform.

### Deep Thinking

When one brain isn't enough, chain multiple models:

```bash
# Enable deep thinking for thorough analysis
inkarms run "Design a distributed system architecture" --deep
```

### Memory & Handoffs

InkArms never forgets (unless you ask nicely):

```bash
# View your conversation memory
inkarms memory list

# Check current session status
inkarms memory status

# Create a snapshot for later
inkarms memory snapshot "api-design-discussion"

# Compact context when it gets too large
inkarms memory compact --strategy summarize

# When context gets full, create a handoff
inkarms memory handoff

# Recover from a handoff
inkarms memory recover
```

### Status & Monitoring

Keep track of your tentacle activities:

```bash
# Check provider health
inkarms status health

# Check all configured providers
inkarms status health --all

# View session token usage
inkarms status tokens

# View session costs
inkarms status cost
```

## Project Status

InkArms Phase 1 is complete! Here's our roadmap:

### Phase 1: Foundation (MVP) ✅
- [x] Project structure and CLI skeleton
- [x] Configuration system (hierarchical loading, profiles, validation)
- [x] Provider layer (LiteLLM integration, fallbacks, secrets, cost tracking)
- [x] Basic skills (loading, parsing, injection)
- [x] Context management (token tracking, compaction, handoffs)
- [x] Security sandbox (whitelist enforcement, path restrictions, audit logging)
- [x] Multi-platform messaging (Telegram, Slack, Discord with polling/WebSocket)
- [x] Tool use & agent loop (bash, file ops, search tools with approval system)
- [x] Advanced tool use (HTTP, Python eval, Git tools, streaming, parallel execution)
- [x] TUI v1 (chat interface, interactive config wizard)

### Phase 2: Intelligence
- [ ] Deep thinking chains
- [ ] LLM-based task classification
- [ ] Smart skill index
- [ ] Plugin system

### Phase 3: Ecosystem
- [ ] Skill marketplace
- [ ] Team profiles
- [ ] Advanced audit & compliance

### Phase 4: Advanced
- [ ] TUI v2 (multi-pane, themes)
- [ ] Async deep thinking
- [ ] CI/CD integration

## Documentation

- [User Guide](docs/user_guide.md) — Get started with InkArms
- [TUI Guide](docs/tui_guide.md) — Interactive chat and configuration wizard
- [Platform Setup](docs/platforms.md) — Telegram, Slack, Discord integration
- [Advanced Tool Use](docs/advanced_tool_use.md) — HTTP, Python, Git tools
- [GitHub Copilot](docs/github_copilot.md) — Use GitHub Copilot as provider
- [Configuration Reference](docs/configuration.md) — All the knobs and dials
- [Security & Sandbox](docs/security.md) — Security features and audit logging
- [Skill Authoring](docs/skill_authoring.md) — Teach InkArms new tricks
- [CLI Reference](docs/cli_reference.md) — Every command, fully documented

## Contributing

We welcome contributions from fellow cephalopod enthusiasts!

```bash
# Clone the repo
git clone https://github.com/digitalzany/inkarms.git
cd inkarms

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check src/ tests/

# Install pre-commit hooks
pre-commit install
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## Maintainers

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/digitalzany">
        <img src="https://github.com/digitalzany.png" width="100px;" alt="Ivan K"/>
        <br />
        <sub><b>digitalzany</b></sub>
      </a>
      <br />
      <sub>Creator</sub>
    </td>
  </tr>
</table>

## Philosophy

```
An octopus doesn't wait for permission.
It reaches out, explores, and adapts.
Each arm thinks independently,
yet all work toward a common goal.

InkArms embodies this spirit:
- Act decisively, but safely
- Remember everything important
- Leave traces of your work
- Coordinate multiple capabilities
- Adapt to any challenge

Be the octopus.
```

## License

MIT License — See [LICENSE](LICENSE) for details.

---

<p align="center">
  <em>Built with 8 arms and lots of ❤️</em>
</p>

<p align="center">
  <a href="https://github.com/digitalzany/inkarms/issues">Issues</a> •
  <a href="https://discord.gg/inkarms">Discord</a>
</p>
