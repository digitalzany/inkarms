# TUI User Guide

InkArms provides a beautiful Terminal User Interface (TUI) built with [Textual](https://textual.textualize.io/) for interactive configuration and chat.

## Quick Start

### Launch Chat Interface

```bash
inkarms chat
```

This opens an interactive chat interface where you can:
- Send messages to the AI
- See streaming responses in real-time
- View tool execution indicators
- Track token usage and costs

### Launch Configuration Wizard

```bash
inkarms config init
```

This opens an interactive configuration wizard with two modes:
- **QuickStart** (2 minutes) - Essential settings only
- **Advanced** (10-15 minutes) - Full configuration

## Chat Interface

### Layout

```
┌─────────────────────────────────────────────────────┐
│  InkArms Chat                              12:34:56 │
├─────────────────────────────────────┬───────────────┤
│                                     │ Session Info  │
│  System                             │               │
│  Welcome to InkArms!                │ Model:        │
│                                     │ claude-sonnet │
│  You · 12:34:00                     │               │
│  Hello!                             │ Tokens: 1,234 │
│                                     │               │
│  AI · 12:34:02                      │ Cost: $0.01   │
│  Hello! How can I help you today?   │               │
│                                     │ Session:      │
│  ⚙️ Executing: http_request...      │ default       │
│                                     │               │
│  AI · 12:34:05                      ├───────────────┤
│  Here's what I found... ▋           │ [Clear Chat]  │
│                                     │ [Exit]        │
├─────────────────────────────────────┴───────────────┤
│ Type your message...                         [Send] │
├─────────────────────────────────────────────────────┤
│ Q: Quit                                             │
└─────────────────────────────────────────────────────┘
```

### Features

**Message Display:**
- User messages shown with primary color border
- AI responses with accent color border
- System messages with warning color border
- Timestamps for each message
- Markdown rendering for AI responses

**Streaming Responses:**
- AI responses update incrementally as tokens arrive
- Cursor indicator (▋) shows response is still generating
- Smooth scrolling to latest message

**Tool Execution:**
- Real-time indicators when tools are running
- Shows tool name: "⚙️ Executing: http_request..."
- Indicators disappear when tool completes

**Session Tracking:**
- Current model displayed
- Token usage counter
- Cost tracking
- Session ID

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Q` | Quit chat |
| `Ctrl+C` | Quit chat |

### Command Options

```bash
# Default session
inkarms chat

# Named session
inkarms chat --session my-project
inkarms chat -s my-project
```

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
| 7. TUI | Theme, animations, timestamps |
| 8. General | Output format, verbose, telemetry |

### Navigation

- **Next →** - Proceed to next section
- **← Back** - Return to previous section
- **Cancel** - Exit wizard without saving
- **Review & Save** - Preview and save configuration

### After Configuration

The wizard creates `~/.inkarms/config.yaml` with all your settings.

Next steps shown on success screen:
1. Set API key (if skipped): `inkarms config set-secret <provider>`
2. Test setup: `inkarms run "Hello!"`
3. Start chatting: `inkarms chat`

## Command Reference

### Chat Command

```bash
inkarms chat [OPTIONS]

Options:
  -s, --session TEXT  Session ID for conversation tracking [default: default]
  --help              Show this message and exit
```

### Config Init Command

```bash
inkarms config init [OPTIONS]

Options:
  -q, --quick  CLI inline wizard (instead of TUI)
  -f, --force  Force overwrite (only valid with --quick)
  --help       Show this message and exit
```

**Modes:**
- Default (no flags): Opens TUI wizard
- `--quick`: CLI inline wizard (questionary prompts)
- `--quick --force`: Non-interactive for automation

## Customization

### Themes

Configure in Advanced wizard Section 7 or `config.yaml`:

```yaml
tui:
  theme: default  # default, light, high_contrast
  enable_animations: true
  show_timestamps: true
```

### Session Management

Sessions track conversation history:

```bash
# Different sessions for different projects
inkarms chat -s project-alpha
inkarms chat -s project-beta

# Sessions persist between runs
inkarms chat -s project-alpha  # Continues previous conversation
```

## Troubleshooting

### TUI Not Displaying Correctly

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

### Input Not Working

**Issue:** Can't type or send messages

**Solutions:**
1. Click in the input field first
2. Make sure focus is on the input area
3. Try resizing terminal window

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
