# Configuration Reference

Welcome to the control room! Here's where you learn to pull all the levers and push all the buttons that make InkArms dance.

## Configuration Hierarchy

InkArms loads configuration from multiple sources, in this order (later overrides earlier):

```
+----------------------------------+  Priority: HIGHEST
|   CLI Flags                      |  --model, --task, --profile
+----------------------------------+
              |
              v
+----------------------------------+
|   Environment Variables          |  INKARMS_MODEL, INKARMS_PROFILE
+----------------------------------+
              |
              v
+----------------------------------+
|   Project Config                 |  ./.inkarms/project.yaml
+----------------------------------+
              |
              v
+----------------------------------+
|   Active Profile                 |  ~/.inkarms/profiles/<name>.yaml
+----------------------------------+
              |
              v
+----------------------------------+  Priority: LOWEST
|   Global Config                  |  ~/.inkarms/config.yaml
+----------------------------------+
```

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Global Config | `~/.inkarms/config.yaml` | Default settings for all projects |
| Profiles | `~/.inkarms/profiles/*.yaml` | Named configuration presets |
| Project Config | `./.inkarms/project.yaml` | Project-specific overrides |
| Skills | `~/.inkarms/skills/` | Installed skills |
| Memory | `~/.inkarms/memory/` | Session logs and handoffs |
| Secrets | `~/.inkarms/secrets/` | Encrypted API keys |
| Audit Log | `~/.inkarms/audit.jsonl` | Activity log |

## Complete Configuration Reference

Here's every configuration option available:

```yaml
# ~/.inkarms/config.yaml - Complete Reference

# =============================================================================
# SYSTEM PROMPT
# =============================================================================
system_prompt:
  # Define the AI's personality
  personality: "You are a helpful AI assistant with expertise in software engineering."

  # Set boundaries and guardrails
  boundaries: "Do not provide legal, medical, or financial advice."

  # Provide context about the user
  user_context: "The user is a software developer working on Python projects."

  # Or use files instead (mutually exclusive with inline)
  # personality_file: "~/.inkarms/prompts/PERSONALITY.md"
  # boundaries_file: "~/.inkarms/prompts/BOUNDARIES.md"
  # user_context_file: "~/.inkarms/prompts/CONTEXT.md"

  # If true, completely replace the model's default system prompt
  overrides_all: false

# =============================================================================
# PROVIDERS
# =============================================================================
providers:
  # Default model for all requests
  default: "anthropic/claude-sonnet-4-20250514"

  # Fallback chain if primary fails
  fallback:
    - "openrouter/anthropic/claude-sonnet-4-20250514"
    - "openai/gpt-4"

  # Model aliases for quick switching
  aliases:
    fast: "openai/gpt-3.5-turbo"
    smart: "anthropic/claude-opus-4-20250514"
    code: "anthropic/claude-sonnet-4-20250514"
    local: "ollama/llama3.1"
    vision: "google/gemini-2.0-flash"

  # API key references (actual keys stored encrypted in secrets/)
  secrets:
    openai: "~/.inkarms/secrets/openai.enc"
    anthropic: "~/.inkarms/secrets/anthropic.enc"

# =============================================================================
# DEEP THINKING
# =============================================================================
deep_thinking:
  enable: true
  cost_warning: true  # Show cost estimate before running

  steps:
    - model: "default"
      context_mode: "full"  # full | answer_only | custom
      prompt_suffix:
        text: "Analyze thoroughly. Identify edge cases."
        enabled: true

    - model: "anthropic/claude-opus-4-20250514"
      context_mode: "answer_only"
      prompt_suffix:
        text: "Critique the previous analysis."
        enabled: true

    - model: "openai/gpt-4"
      context_mode: "full"
      prompt_suffix:
        text: "Synthesize the best recommendations."
        enabled: true

# =============================================================================
# TASK ROUTING
# =============================================================================
task_routing:
  enable: true
  classification_method: "heuristic"  # heuristic | llm | explicit_only
  confidence_threshold: 0.80

  # Map task types to models
  categories:
    coding: "anthropic/claude-opus-4-20250514"
    image: "google/gemini-2.0-flash"
    consulting: "google/gemini-2.0-flash"
    data_analysis: "openai/gpt-4"
    documentation: "anthropic/claude-sonnet-4-20250514"
    default: "anthropic/claude-sonnet-4-20250514"

  # Keyword patterns for heuristic classification
  heuristics:
    coding:
      - "debug|fix|code|function|class|error|bug|implement"
      - "python|javascript|typescript|rust|go"
    image:
      - "generate|create|draw|image|picture|diagram"
    consulting:
      - "strategy|market|analysis|business|plan|advise"

# =============================================================================
# CONTEXT MANAGEMENT
# =============================================================================
context:
  # Thresholds as percentage of max context window
  auto_compact_threshold: 0.70
  handoff_threshold: 0.85

  compaction:
    strategy: "summarize"  # summarize | truncate | sliding_window
    preserve_recent_turns: 5
    summary_model: "openai/gpt-3.5-turbo"  # Use cheaper model

  memory_path: "~/.inkarms/memory"
  daily_logs: true

  handoff:
    auto_recover: true  # Load HANDOFF.md on startup
    archive_path: "~/.inkarms/memory"

# =============================================================================
# SECURITY
# =============================================================================
security:
  sandbox:
    enable: true
    mode: "whitelist"  # whitelist | blacklist | prompt | disabled

  # Allowed commands (whitelist mode)
  whitelist:
    - "ls"
    - "cat"
    - "head"
    - "tail"
    - "grep"
    - "find"
    - "echo"
    - "mkdir"
    - "cp"
    - "mv"
    - "git"
    - "python"
    - "pip"
    - "npm"
    - "node"

  # Blocked patterns (blacklist mode)
  blacklist:
    - "rm -rf"
    - "sudo"
    - "chmod"
    - "chown"
    - "curl | bash"
    - "wget | bash"

  # Path restrictions
  restricted_paths:
    read_only:
      - "/etc"
      - "/usr"
    no_access:
      - "/root"
      - "~/.ssh"
      - "~/.gnupg"
      - "~/.inkarms/secrets"

  # Audit logging
  audit_log:
    enable: true
    path: "~/.inkarms/audit.jsonl"
    rotation: "daily"  # daily | weekly | size
    retention_days: 90
    include_responses: false  # Warning: large!

# =============================================================================
# SKILLS
# =============================================================================
skills:
  local_path: "~/.inkarms/skills"
  project_path: "./.inkarms/skills"

  smart_index:
    enable: true
    mode: "keyword"  # keyword | llm | off
    max_skills_per_query: 3
    index_path: "~/.inkarms/skills/index.json"

  auto_update:
    enable: false
    check_interval_hours: 24

# =============================================================================
# UI
# =============================================================================
ui:
  # Backend selection (auto prefers Rich, falls back to Textual)
  backend: "auto"  # auto | rich | textual

  # Theme
  theme: "default"

  # Display options
  show_status_bar: true
  show_timestamps: true
  max_messages_display: 20  # 5-100

  # Input options
  enable_mouse: true
  enable_completion: true

# Legacy TUI config (still recognized for backward compatibility)
# tui:
#   enable: true
#   theme: "dark"
#   keybindings: "default"
#   chat:
#     show_timestamps: true
#     show_token_count: true
#     show_cost: true
#   status_bar:
#     show_model: true
#     show_context_usage: true
#     show_session_cost: true

# =============================================================================
# COST TRACKING
# =============================================================================
cost:
  budgets:
    daily: 10.00     # USD
    monthly: 200.00  # USD

  alerts:
    warning_threshold: 0.80  # Warn at 80% of budget
    block_on_exceed: false   # Don't block, just warn

# =============================================================================
# GENERAL
# =============================================================================
general:
  default_profile: null  # Or "dev", "prod", etc.

  output:
    format: "rich"  # rich | plain | json
    color: true
    verbose: false

  storage:
    backend: "file"  # file | sqlite
    sqlite_path: "~/.inkarms/data.db"
```

## Environment Variables

All config options can be overridden via environment variables:

```bash
# Pattern: INKARMS_<SECTION>_<KEY>
export INKARMS_PROVIDERS_DEFAULT="openai/gpt-4"
export INKARMS_SECURITY_SANDBOX_ENABLE="false"
export INKARMS_PROFILE="dev"

# Provider API keys (standard names)
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
```

## Profile Configuration

Profiles are partial configs that override global settings:

```yaml
# ~/.inkarms/profiles/dev.yaml
_meta:
  name: "dev"
  description: "Development profile with local model"

providers:
  default: "ollama/llama3.1"

security:
  sandbox:
    mode: "prompt"  # Ask before running commands

general:
  output:
    verbose: true
```

Use profiles:

```bash
# Temporarily
inkarms run "Query" --profile dev

# Set as default
inkarms profile use dev --default
```

## Project Configuration

Create `.inkarms/project.yaml` in your project root:

```yaml
# .inkarms/project.yaml
_meta:
  name: "my-web-app"
  description: "Project-specific config"

providers:
  default: "anthropic/claude-opus-4-20250514"

# Use + prefix to APPEND to global lists
security:
  +whitelist:
    - "docker"
    - "docker-compose"
    - "npm run"

# Use - prefix to REMOVE from global lists
# -whitelist:
#   - "rm"

# Define project-specific routing
task_routing:
  +heuristics:
    frontend:
      - "react|vue|angular|css|html"
```

## CLI Config Commands

### Initialization

```bash
# Initialize InkArms (creates ~/.inkarms/ directory and default config)
inkarms config init

# Initialize project config in current directory
inkarms config init --project

# Create a new profile
inkarms config init --profile work

# Force re-initialization (overwrites existing)
inkarms config init --force
```

### Viewing Configuration

```bash
# Show all config (YAML format)
inkarms config show

# Show specific section
inkarms config show providers
inkarms config show security.whitelist

# Show as JSON
inkarms config show --json

# Show configuration file locations
inkarms config show --sources

# Use a specific profile
inkarms config show --profile dev
```

### Modifying Configuration

```bash
# Set a value in global config
inkarms config set providers.default "openai/gpt-4"

# Set in specific scope
inkarms config set --scope profile --profile dev providers.default "ollama/llama3.1"
inkarms config set --scope project providers.default "claude-opus"

# Set boolean values
inkarms config set security.sandbox.enable false

# Set arrays (use JSON format)
inkarms config set security.whitelist '["ls", "cat", "git"]'

# Edit in your editor
inkarms config edit
inkarms config edit --profile dev
inkarms config edit --project
```

### Validation

```bash
# Validate merged configuration
inkarms config validate

# Validate specific file
inkarms config validate --file ./custom-config.yaml

# Validate with a profile
inkarms config validate --profile dev
```

## Secrets Management

Never put API keys in config files! Use the encrypted secrets manager:

```bash
# Set a secret (prompts securely for the value)
inkarms config set-secret anthropic

# Or provide the value directly (less secure - shows in history)
inkarms config set-secret anthropic --value "sk-ant-..."

# List configured secrets (shows names and env var mappings, not values)
inkarms config list-secrets

# Delete a secret
inkarms config delete-secret anthropic
```

### How It Works

Secrets are encrypted using Fernet symmetric encryption:
- A master key is generated on first use and stored in `~/.inkarms/secrets/master.key`
- Each secret is encrypted and stored as `~/.inkarms/secrets/<name>.enc`
- The secrets directory has restricted permissions (0700)
- Secrets are automatically loaded into environment variables when InkArms runs

### Environment Variable Mapping

| Provider | Environment Variable |
|----------|---------------------|
| openai | `OPENAI_API_KEY` |
| anthropic | `ANTHROPIC_API_KEY` |
| google | `GOOGLE_API_KEY` |
| openrouter | `OPENROUTER_API_KEY` |
| huggingface | `HUGGINGFACE_API_KEY` |
| mistral | `MISTRAL_API_KEY` |
| groq | `GROQ_API_KEY` |
| together | `TOGETHER_API_KEY` |
| custom | `CUSTOM_API_KEY` |

## Tips

### 1. Start Simple

Don't configure everything at once. Start with:

```yaml
providers:
  default: "anthropic/claude-sonnet-4-20250514"

security:
  sandbox:
    enable: true
    mode: whitelist
  whitelist:
    - ls
    - cat
    - git
```

### 2. Use Profiles for Context Switching

```yaml
# ~/.inkarms/profiles/work.yaml - Strict settings
security:
  sandbox:
    mode: whitelist

# ~/.inkarms/profiles/personal.yaml - More relaxed
security:
  sandbox:
    mode: prompt
```

### 3. Project Configs for Consistency

Team members using the same `.inkarms/project.yaml` ensures consistent behavior.

---

*"Configuration is art. May your YAML be valid and your keys be secret."* 🐙
