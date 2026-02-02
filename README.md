# 🐙 InkArms - Your personal AI agent

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

# From source (for the adventurous)
git clone https://github.com/digitalzany/inkarms.git
cd inkarms
pip install -e ".[dev]"
```

### Your First Tentacle Wave

```bash
# Check if InkArms is ready to embrace you
inkarms --version

# See all the arms at your disposal
inkarms --help

# Ask InkArms to do something (requires API key setup)
inkarms run "Explain quantum computing like I'm a curious octopus"

# Launch the beautiful TUI (coming soon!)
inkarms tui
```

### Configuration

InkArms looks for configuration in these places (in order of priority):

1. CLI flags (`--model`, `--profile`, etc.)
2. Environment variables (`INKARMS_*`)
3. Project config (`./.inkarms/project.yaml`)
4. Active profile (`~/.inkarms/profiles/<name>.yaml`)
5. Global config (`~/.inkarms/config.yaml`)

Set up your first API key:

```bash
# Set your API key (will prompt securely)
inkarms config set-secret anthropic

# Or use environment variables
export ANTHROPIC_API_KEY="your-key-here"
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

# Create a snapshot for later
inkarms memory snapshot "api-design-discussion"

# When context gets full, create a handoff
inkarms memory handoff
```

### Status & Monitoring

Keep track of your tentacle activities:

```bash
# Check provider health
inkarms status health

# View token usage
inkarms status tokens --today

# Monitor costs
inkarms status cost --month
```

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
