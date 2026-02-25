# UI Guide

InkArms provides an interactive terminal interface with a pluggable backend system. The default backend uses [Rich](https://github.com/Textualize/rich) for rendering and [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) for full-screen layout and input handling.

## Quick Start

### Launch the UI

```bash
# Simply run inkarms with no arguments
inkarms
```

This opens the main menu where you can:
- Start a new chat or continue an existing session
- View the dashboard with session stats and provider status
- Manage sessions
- Run the configuration wizard
- Adjust settings

### Launch Configuration Wizard

```bash
inkarms config init
```

This opens an interactive configuration wizard with three modes:
- **QuickStart** (2 minutes) - Essential settings only
- **Advanced** (10-15 minutes) - Full configuration
- **Skip Setup** - Configure manually later

## Chat Interface

### Layout

```
+-----------------------------------------------------+
|  InkArms Chat                              12:34:56  |
+-----------------------------------------------------+
|                                                       |
|  System                                               |
|  Welcome to InkArms!                                  |
|                                                       |
|  You - 12:34:00                                       |
|  Hello!                                               |
|                                                       |
|  AI - 12:34:02                                        |
|  Hello! How can I help you today?                     |
|                                                       |
+-----------------------------------------------------+
|  Provider: anthropic | Model: claude-sonnet | $0.01  |
+-----------------------------------------------------+
|  > Type your message... (Enter to send)              |
+-----------------------------------------------------+
```

### Features

**Message Display:**
- User messages shown with primary color styling
- AI responses with accent color and full markdown rendering
- System messages with warning color styling
- Syntax-highlighted code blocks
- Timestamps for each message

**Streaming Responses:**
- AI responses update incrementally as tokens arrive
- Cursor indicator shows response is still generating
- Smooth scrolling to latest message

**Tool Execution (Agent Mode):**
- When tools are enabled, queries go through the agent loop instead of direct streaming
- Collapsed Rich panels show each tool's name, execution time, and output
- Real-time status indicator (e.g., "Running execute_bash...") while a tool is active
- Dangerous tools prompt for approval inline — press `a` to allow, `d` to deny, or `A` to allow all for the session
- Tool panels use color-coded borders: green for success, red for errors, yellow for denied

**Session Tracking:**
- Current provider and model displayed in status bar
- Token usage counter
- Cost tracking
- Session name
- Tools indicator showing count and approval mode (e.g., "Tools: 8 (manual)")

### Slash Commands

Type `/` in the chat input to access commands (with tab completion):

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/menu` | Return to main menu |
| `/dashboard` | Show dashboard view |
| `/sessions` | Manage sessions |
| `/config` | Open configuration wizard |
| `/clear` | Clear conversation history |
| `/usage` | Show token/cost usage |
| `/status` | Show provider status |
| `/model <name>` | Switch model |
| `/model` | Show current model |
| `/save` | Save current session |
| `/load` | Load a session |
| `/history` | Show conversation history |
| `/chat` | Return to chat view |
| `/tools` | Show registered tools and their status |
| `/agent` | Show/change agent settings (`on`, `off`, `auto`, `manual`, `disabled`) |
| `/quit` | Exit InkArms |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Tab` | Autocomplete slash commands |
| `a` | Allow a pending tool execution (only shown during approval prompt) |
| `d` | Deny a pending tool execution (only shown during approval prompt) |
| `A` | Allow all tools for the rest of the session (only shown during approval prompt) |
| `Ctrl+C` | Exit |

## Views

The UI provides several views accessible from the main menu or via slash commands:

| View | Description |
|------|-------------|
| **Menu** | Main navigation hub (shown on startup) |
| **Chat** | Conversational AI interface |
| **Dashboard** | Session stats, provider status |
| **Sessions** | Create, switch, and manage sessions |
| **Config** | Configuration wizard (QuickStart + Advanced) |
| **Settings** | Quick settings adjustments |

## Configuration Wizard

### QuickStart Mode (Recommended)

Three sections to get started in minutes:

**Provider Setup**
- Select your AI provider (Anthropic, OpenAI, Gemini, Ollama, ...)
- Choose your default model
- Enter (or confirm) your API key — stored encrypted
- Enable or disable automatic model discovery from the provider API

**Security**
- Whitelist mode (most secure — only listed commands are allowed)
- Blacklist mode (default — dangerous patterns are blocked)
- Prompt mode (ask before each command executes)
- Disabled (development only)

**Summary**
- Review your choices and save to `~/.inkarms/config.yaml`

### Advanced Mode

Non-linear section menu — jump to any section, configure it, and return. All 8 sections:

| Section | Settings |
|---------|----------|
| 1. Provider | Default model, API key, model discovery |
| 2. Security | Sandbox mode, path restrictions |
| 3. Tools | Web Search (Brave API key) |
| 4. Agent | Tool approval mode, max iterations |
| 5. Context | Compaction strategy, auto-compact threshold |
| 6. Cost | Daily budget, block on budget exceed |
| 7. Hub | Enable hub daemon, port, localhost trust |
| 8. Platforms | Telegram, Slack, Discord tokens |

### Navigation

- **Next** - Proceed to next section
- **Back** - Return to previous section
- **Cancel** - Exit wizard without saving
- **Review & Save** - Preview and save configuration

### After Configuration

The wizard creates `~/.inkarms/config.yaml` with all your settings.

Next steps shown on success screen:
1. Set API key (if skipped): `inkarms config set-secret <provider>`
2. Test setup: `inkarms run "Hello!"`
3. Start the UI: `inkarms`

## Backend Selection

InkArms uses the **Rich** backend (Rich + prompt_toolkit), included in the base install. Select it explicitly if needed:

```bash
# Via CLI flag
inkarms --ui rich

# Via explicit ui command
inkarms ui --backend rich

# Via config
# ~/.inkarms/config.yaml
ui:
  backend: "auto"  # auto | rich
```

In `auto` mode (default), InkArms uses Rich.

## Command Reference

### Launch UI (Default)

```bash
inkarms [OPTIONS]

Options:
  --ui [auto|rich]  UI backend to use [default: auto]
  -V, --version     Show version
  -p, --profile     Use specific config profile
  --no-color        Disable colored output
  --help            Show this message and exit
```

### Launch UI (Explicit)

```bash
inkarms ui [OPTIONS]

Options:
  -b, --backend [auto|rich]  UI backend [default: auto]
  --help                     Show this message and exit
```

### Config Init Command

```bash
inkarms config init [OPTIONS]

Options:
  -q, --quick  CLI inline wizard (instead of interactive UI)
  -f, --force  Force overwrite (only valid with --quick)
  --help       Show this message and exit
```

**Modes:**
- Default (no flags): Opens interactive UI wizard
- `--quick`: CLI inline wizard (questionary prompts)
- `--quick --force`: Non-interactive for automation

## Customization

### UI Configuration

Configure in `~/.inkarms/config.yaml`:

```yaml
ui:
  backend: "auto"         # auto | rich
  theme: "default"        # Theme name
  show_status_bar: true   # Show status bar in chat
  show_timestamps: true   # Show message timestamps
  max_messages_display: 20  # Messages to display (5-100)
  enable_mouse: true      # Enable mouse support
  enable_completion: true # Enable slash command completion
```

### Session Management

Sessions track conversation history:

```bash
# Sessions are managed through the UI
inkarms
# Then use /sessions slash command or Sessions menu item

# Sessions persist between runs
# Switch between sessions for different projects
```

## Troubleshooting

### UI Not Displaying Correctly

**Issue:** Characters or layout broken

**Solutions:**
1. Ensure terminal supports UTF-8
2. Use a modern terminal (iTerm2, Windows Terminal, Alacritty)
3. Increase terminal size (minimum 80x24 recommended)

### Colors Not Showing

**Issue:** No colors or wrong colors

**Solutions:**
1. Check terminal supports 256 colors: `echo $TERM`
2. Try: `export TERM=xterm-256color`
3. Use `--no-color` flag for plain output

### OAuth Not Working (GitHub Copilot)

**Issue:** Device flow doesn't complete

**Solutions:**
1. Check internet connection
2. Ensure GitHub Copilot subscription is active
3. Try in a new terminal session
4. Check for firewall blocking github.com

## See Also

- [Configuration Guide](configuration.md) - Full configuration reference
- [CLI Reference](cli_reference.md) - All CLI commands
- [GitHub Copilot](github_copilot.md) - GitHub Copilot setup
- [Security Guide](security.md) - Sandbox and audit settings
