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

**Tool Execution:**
- Real-time indicators when tools are running
- Shows tool name during execution
- Indicators disappear when tool completes

**Session Tracking:**
- Current provider and model displayed in status bar
- Token usage counter
- Cost tracking
- Session name

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
| `/quit` | Exit InkArms |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Tab` | Autocomplete slash commands |
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

4 simple steps to get started:

**Step 1: Choose Provider**
- Anthropic Claude (Recommended)
- OpenAI
- GitHub Copilot
- Other

**Step 2: API Key Setup**
- Enter your API key (encrypted storage)
- Skip for GitHub Copilot (uses OAuth)
- Or configure later

**Step 3: Security Configuration**
- Whitelist mode (most secure)
- Blacklist mode
- Prompt mode
- Disabled (development only)

**Step 4: Tool Configuration**
- Enable/disable tool execution
- HTTP, Python, Git tools

### Advanced Mode

8 comprehensive sections:

| Section | Settings |
|---------|----------|
| 1. Provider | Model, fallback, timeout, retries |
| 2. Context | Compaction strategy, thresholds, handoffs |
| 3. Security | Sandbox mode, path restrictions, audit log |
| 4. Tools | Enable tools, approval mode, iterations |
| 5. Skills | Enable skills, auto-inject, indexing |
| 6. Cost | Cost tracking, daily/monthly budgets |
| 7. UI | Theme, status bar, timestamps |
| 8. General | Output format, verbose, telemetry |

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

InkArms supports multiple UI backends:

| Backend | Description | Dependencies |
|---------|-------------|-------------|
| **Rich** (default) | Rich + prompt_toolkit | Included in base install |
| **Textual** (optional) | Textual framework | `pip install inkarms[textual]` |

Select the backend via CLI flag or config:

```bash
# Via CLI flag
inkarms --ui rich
inkarms --ui textual

# Via explicit ui command
inkarms ui --backend rich

# Via config
# ~/.inkarms/config.yaml
ui:
  backend: "auto"  # auto | rich | textual
```

In `auto` mode (default), InkArms prefers Rich and falls back to Textual if available.

## Command Reference

### Launch UI (Default)

```bash
inkarms [OPTIONS]

Options:
  --ui [auto|rich|textual]  UI backend to use [default: auto]
  -V, --version             Show version
  -v, --verbose             Enable verbose output
  -q, --quiet               Minimal output
  -p, --profile TEXT        Use specific config profile
  --no-color                Disable colored output
  --help                    Show this message and exit
```

### Launch UI (Explicit)

```bash
inkarms ui [OPTIONS]

Options:
  -b, --backend [auto|rich|textual]  UI backend [default: auto]
  --help                             Show this message and exit
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
  backend: "auto"         # auto | rich | textual
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

### Trying Textual Backend

**Issue:** Want to try the Textual backend

**Solutions:**
1. Install: `pip install inkarms[textual]`
2. Launch: `inkarms --ui textual`
3. Note: Textual backend is not yet fully implemented; use Rich (default) for production use

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
