# Multi-Platform Messaging Setup Guide

This guide will help you set up InkArms to work with various messaging platforms like Telegram, Slack, Discord, and more.

---

## Overview

InkArms supports interaction through multiple messaging platforms, allowing you to chat with your AI assistant from your favorite messaging app. Each platform runs independently using polling or WebSocket connections - **no webhook server required** for personal use.

**Supported Platforms:**
- ✅ **Telegram** - Bot API with long polling
- ✅ **Slack** - Socket Mode (WebSocket)
- ✅ **Discord** - Gateway WebSocket
- 🚧 **WhatsApp** - Business API (requires webhook)
- 🚧 **iMessage** - macOS only (local)
- 🚧 **Signal** - signal-cli integration
- 🚧 **Microsoft Teams** - Bot Framework
- 🚧 **WeChat** - Official Account API

> **Note:** ✅ = Ready to use, 🚧 = Planned for future release

---

## Prerequisites

### 1. Install Platform Dependencies

```bash
# Install InkArms with platform support
pip install -e ".[platforms]"

# Or install specific platforms only
pip install python-telegram-bot  # Telegram
pip install slack-sdk             # Slack
pip install discord.py            # Discord
```

### 2. Enable Platforms in Configuration

Edit `~/.inkarms/config.yaml`:

```yaml
platforms:
  enable: true  # Enable platform messaging globally
```

---

## Telegram Bot Setup

### Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow the prompts:
   - **Bot name**: "My InkArms Assistant" (display name)
   - **Bot username**: "my_inkarms_bot" (must end with 'bot')
4. **Save the bot token** - you'll need it for configuration

Example token: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### Step 2: Configure InkArms

Add to `~/.inkarms/config.yaml`:

```yaml
platforms:
  enable: true

  telegram:
    enable: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"  # Or paste token directly
    mode: polling  # Uses long polling (no webhook needed)
    polling_interval: 2  # Check for messages every 2 seconds
    parse_mode: "MarkdownV2"  # Format responses with Markdown

    # Optional: Restrict to specific users
    allowed_users: []  # Empty = all users allowed
    # allowed_users: ["123456789"]  # Only this Telegram user ID
```

### Step 3: Set Environment Variable (Recommended)

```bash
# Add to ~/.bashrc or ~/.zshrc
export TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
```

Or use secrets management:

```bash
inkarms config set-secret telegram TELEGRAM_BOT_TOKEN
```

### Step 4: Start the Bot

```bash
# Start all enabled platforms
inkarms platforms start

# Or start only Telegram
inkarms platforms start --platform telegram
```

### Step 5: Test It

1. Open Telegram
2. Search for your bot username (e.g., `@my_inkarms_bot`)
3. Start a conversation: `/start`
4. Send a message: "Hello! What's the weather like?"
5. Your bot should respond with AI-generated text

### Telegram Features

- ✅ **Streaming responses** - Responses update in real-time
- ✅ **Markdown formatting** - Rich text with code blocks, lists, etc.
- ✅ **Typing indicators** - Shows "typing..." while processing
- ✅ **User whitelisting** - Restrict access to specific users
- ✅ **Rate limiting** - Prevents spam

### Finding Your Telegram User ID

If you want to restrict access, you need your user ID:

1. Send a message to your bot
2. Check the InkArms console output:
   ```
   telegram | 123456789: Hello!
   ```
3. The number `123456789` is your user ID
4. Add it to `allowed_users` in config

---

## Slack Bot Setup

### Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. **App Name**: "InkArms Assistant"
4. **Workspace**: Select your workspace
5. Click **"Create App"**

### Step 2: Configure Bot Permissions

1. In the left sidebar, click **"OAuth & Permissions"**
2. Scroll to **"Scopes"** → **"Bot Token Scopes"**
3. Add these scopes:
   - `chat:write` - Send messages
   - `channels:history` - Read channel messages
   - `groups:history` - Read private channel messages
   - `im:history` - Read direct messages
   - `mpim:history` - Read group messages
   - `users:read` - Read user information
4. Scroll up and click **"Install to Workspace"**
5. Click **"Allow"**
6. **Save the Bot User OAuth Token** (starts with `xoxb-`)

### Step 3: Enable Socket Mode

1. In the left sidebar, click **"Socket Mode"**
2. Toggle **"Enable Socket Mode"** to ON
3. **Token Name**: "InkArms Socket Token"
4. Click **"Generate"**
5. **Save the App-Level Token** (starts with `xapp-`)

### Step 4: Subscribe to Events

1. In the left sidebar, click **"Event Subscriptions"**
2. Toggle **"Enable Events"** to ON
3. Expand **"Subscribe to bot events"**
4. Add these events:
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`
5. Click **"Save Changes"**

### Step 5: Configure InkArms

Add to `~/.inkarms/config.yaml`:

```yaml
platforms:
  enable: true

  slack:
    enable: true
    bot_token: "${SLACK_BOT_TOKEN}"      # xoxb-... token
    app_token: "${SLACK_APP_TOKEN}"      # xapp-... token
    mode: socket  # Uses Socket Mode (WebSocket)

    # Optional: Restrict to specific channels
    allowed_channels: []  # Empty = all channels
    # allowed_channels: ["C123456789"]  # Only this channel ID
```

### Step 6: Set Environment Variables

```bash
export SLACK_BOT_TOKEN="xoxb-1234567890-..."
export SLACK_APP_TOKEN="xapp-1-A0123456789-..."
```

### Step 7: Start the Bot

```bash
inkarms platforms start --platform slack
```

### Step 8: Test It

1. Open Slack
2. Invite the bot to a channel: `/invite @InkArms Assistant`
3. Or send a direct message to the bot
4. Send: "Hello! Summarize this conversation."
5. The bot should respond

### Slack Features

- ✅ **Socket Mode** - No webhook or public IP required
- ✅ **Streaming responses** - Live message updates
- ✅ **Thread support** - Maintains conversation context
- ✅ **Markdown (mrkdwn)** - Slack-specific formatting
- ✅ **Channel restrictions** - Control where bot can respond
- ✅ **Rate limiting** - Per-user message limits

### Finding Slack Channel IDs

To restrict bot to specific channels:

1. Right-click on channel name
2. Select **"View channel details"**
3. Look for the channel ID at the bottom (e.g., `C0123456789`)
4. Add to `allowed_channels` in config

---

## Discord Bot Setup

### Step 1: Create a Discord Application

1. Go to https://discord.com/developers/applications
2. Click **"New Application"**
3. **Name**: "InkArms Assistant"
4. Click **"Create"**

### Step 2: Create a Bot

1. In the left sidebar, click **"Bot"**
2. Click **"Add Bot"** → **"Yes, do it!"**
3. Under **"Privileged Gateway Intents"**, enable:
   - ✅ **Message Content Intent** (required to read messages)
4. Under **"Token"**, click **"Reset Token"** → **"Copy"**
5. **Save the bot token** - you'll need it

### Step 3: Get Bot Invite Link

1. In the left sidebar, click **"OAuth2"** → **"URL Generator"**
2. Under **"Scopes"**, select:
   - ✅ `bot`
3. Under **"Bot Permissions"**, select:
   - ✅ Read Messages/View Channels
   - ✅ Send Messages
   - ✅ Send Messages in Threads
   - ✅ Read Message History
4. Copy the generated URL at the bottom

### Step 4: Invite Bot to Your Server

1. Paste the URL from step 3 into your browser
2. Select your server
3. Click **"Authorize"**
4. Complete the CAPTCHA

### Step 5: Configure InkArms

Add to `~/.inkarms/config.yaml`:

```yaml
platforms:
  enable: true

  discord:
    enable: true
    bot_token: "${DISCORD_BOT_TOKEN}"
    mode: gateway  # Uses Gateway WebSocket
    command_prefix: "!"  # Optional command prefix

    # Optional: Restrict to specific servers/channels
    allowed_guilds: []  # Empty = all servers
    allowed_channels: []  # Empty = all channels
    # allowed_guilds: ["123456789012345678"]
    # allowed_channels: ["987654321098765432"]
```

### Step 6: Set Environment Variable

```bash
export DISCORD_BOT_TOKEN="your_token"
```

### Step 7: Start the Bot

```bash
inkarms platforms start --platform discord
```

### Step 8: Test It

1. Open Discord
2. Go to a channel where the bot has access
3. Mention the bot: `@InkArms Assistant hello!`
4. Or use command prefix: `!what is Python?`
5. The bot should respond

### Discord Features

- ✅ **Gateway WebSocket** - Real-time connection
- ✅ **Streaming responses** - Live message updates
- ✅ **Standard Markdown** - Code blocks, formatting
- ✅ **Guild/channel restrictions** - Control bot access
- ✅ **Typing indicators** - Shows when bot is thinking
- ✅ **Rate limiting** - Prevents spam

### Finding Discord IDs

Enable Developer Mode first:
1. **User Settings** → **Advanced** → **Developer Mode**: ON

To find Guild (Server) ID:
1. Right-click on server icon
2. Click **"Copy Server ID"**

To find Channel ID:
1. Right-click on channel name
2. Click **"Copy Channel ID"**

---

## Configuration Reference

### Global Platform Settings

```yaml
platforms:
  enable: true  # Master switch for all platforms

  # Rate limiting (applies to all platforms)
  rate_limit_per_user: 10  # Max messages per minute per user
  max_concurrent_sessions: 100  # Max simultaneous conversations
```

### Telegram Configuration

```yaml
platforms:
  telegram:
    enable: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    mode: polling  # or "webhook" (requires public URL)
    polling_interval: 2  # Seconds between checks
    parse_mode: "MarkdownV2"  # Message formatting
    allowed_users: []  # User ID whitelist (empty = all)
```

### Slack Configuration

```yaml
platforms:
  slack:
    enable: true
    bot_token: "${SLACK_BOT_TOKEN}"  # xoxb- token
    app_token: "${SLACK_APP_TOKEN}"  # xapp- token
    mode: socket  # Socket Mode (recommended)
    allowed_channels: []  # Channel ID whitelist (empty = all)
```

### Discord Configuration

```yaml
platforms:
  discord:
    enable: true
    bot_token: "${DISCORD_BOT_TOKEN}"
    mode: gateway  # Gateway WebSocket
    command_prefix: "!"  # Optional prefix for commands
    allowed_guilds: []  # Server ID whitelist (empty = all)
    allowed_channels: []  # Channel ID whitelist (empty = all)
```

---

## Managing Platform Bots

### List Available Platforms

```bash
inkarms platforms list
```

Output:
```
Available Platforms
┏━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Platform ┃ Status   ┃ Mode              ┃ Configuration ┃
┡━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ Telegram │ Enabled  │ Long Polling      │ ✓ Configured  │
│ Slack    │ Enabled  │ Socket Mode       │ ✓ Configured  │
│ Discord  │ Enabled  │ Gateway WebSocket │ ✓ Configured  │
└──────────┴──────────┴───────────────────┴───────────────┘
```

### Start All Platforms

```bash
inkarms platforms start
```

### Start Specific Platform

```bash
inkarms platforms start --platform telegram
inkarms platforms start --platform slack
inkarms platforms start --platform discord
```

### Check Status

```bash
inkarms platforms status
```

### Stop Platforms

Press `Ctrl+C` in the terminal where platforms are running.

---

## Troubleshooting

### Common Issues

#### Bot doesn't respond

1. **Check configuration**:
   ```bash
   inkarms platforms list
   ```
   Ensure platform shows "✓ Configured"

2. **Check console output** for errors when starting:
   ```bash
   inkarms platforms start --platform telegram
   ```

3. **Verify token** is correct in config or environment

4. **Check user whitelist** - if `allowed_users` is set, your user ID must be in the list

#### "Missing token" error

```bash
# Set environment variable
export TELEGRAM_BOT_TOKEN="your-token-here"

# Or use secrets management
inkarms config set-secret telegram TELEGRAM_BOT_TOKEN
```

#### "Platform adapter not available" error

```bash
# Install missing platform library
pip install python-telegram-bot  # Telegram
pip install slack-sdk             # Slack
pip install discord.py            # Discord
```

#### Rate limit exceeded

If users are being rate limited:

1. Increase rate limit in config:
   ```yaml
   platforms:
     rate_limit_per_user: 20  # Increase from 10
   ```

2. Reset rate limit for specific user:
   ```bash
   # Currently requires restart
   # Future: inkarms platforms reset-limit <user>
   ```

#### Bot appears offline

**Telegram:**
- Check token is valid
- Ensure polling_interval isn't too high
- Bot may appear offline until first message

**Slack:**
- Ensure Socket Mode is enabled
- Check both bot_token and app_token are set
- Verify app is installed in workspace

**Discord:**
- Ensure bot has required permissions
- Check "Message Content Intent" is enabled
- Verify bot is invited to server/channel

### Debug Mode

Enable verbose logging:

```yaml
# In config.yaml
logging:
  level: DEBUG
```

Or run with verbose flag:
```bash
inkarms platforms start --verbose
```

### Testing Tokens

#### Test Telegram Token

```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getMe
```

Should return bot info if valid.

#### Test Slack Token

```bash
curl -H "Authorization: Bearer xoxb-YOUR-TOKEN" \
  https://slack.com/api/auth.test
```

Should return `"ok": true` if valid.

---

## Security Best Practices

### 1. Use Environment Variables

**Don't** hardcode tokens in config files:
```yaml
# ❌ Bad
bot_token: "1234567890:ABCdefGHI..."
```

**Do** use environment variables:
```yaml
# ✅ Good
bot_token: "${TELEGRAM_BOT_TOKEN}"
```

### 2. Restrict Access

Use whitelists for production bots:

```yaml
telegram:
  allowed_users: ["123456789"]  # Only your user ID

slack:
  allowed_channels: ["C0123456"]  # Specific channel only

discord:
  allowed_guilds: ["987654321"]  # Your server only
```

### 3. Enable Rate Limiting

Prevent abuse:

```yaml
platforms:
  rate_limit_per_user: 10  # 10 messages per minute
```

### 4. Monitor Audit Logs

Check who's using your bot:

```bash
cat ~/.inkarms/logs/audit.jsonl | jq 'select(.event | startswith("platform_"))'
```

### 5. Keep Tokens Secure

- Never commit tokens to git
- Add `config.yaml` to `.gitignore` if it contains tokens
- Use secrets management:
  ```bash
  inkarms config set-secret telegram TELEGRAM_BOT_TOKEN
  ```

---

## Advanced Configuration

### Custom Rate Limits Per Platform

```yaml
platforms:
  telegram:
    # Platform-specific rate limit
    rate_limit_per_second: 1  # Max 1 message per second

  slack:
    rate_limit_per_second: 2  # Max 2 messages per second
```

### Multiple Bots

Run different bots by using different config profiles:

```bash
# Create profiles
mkdir -p ~/.inkarms/profiles

# telegram-bot.yaml
cat > ~/.inkarms/profiles/telegram-bot.yaml << EOF
platforms:
  telegram:
    enable: true
  slack:
    enable: false
  discord:
    enable: false
EOF

# Start with profile
inkarms --profile telegram-bot platforms start
```

### Running as Service

Create systemd service (Linux):

```ini
# /etc/systemd/system/inkarms-platforms.service
[Unit]
Description=InkArms Platform Bots
After=network.target

[Service]
Type=simple
User=youruser
Environment="TELEGRAM_BOT_TOKEN=your-token"
Environment="SLACK_BOT_TOKEN=your-token"
Environment="SLACK_APP_TOKEN=your-token"
Environment="DISCORD_BOT_TOKEN=your-token"
ExecStart=/usr/local/bin/inkarms platforms start
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable inkarms-platforms
sudo systemctl start inkarms-platforms
sudo systemctl status inkarms-platforms
```

---

## Next Steps

- **Configure AI Provider**: Set up your OpenAI/Anthropic API key
  ```bash
  inkarms config set-secret anthropic ANTHROPIC_API_KEY
  ```

- **Add Skills**: Install skills for specific capabilities
  ```bash
  inkarms skill install code-review
  ```

- **Customize Personality**: Edit system prompt in config
  ```yaml
  system_prompt:
    personality: "You are a helpful coding assistant."
  ```

- **Enable Audit Logging**: Track all interactions
  ```yaml
  security:
    audit_log:
      enable: true
  ```

---

## Support & Resources

- **Documentation**: `docs/` directory
- **CLI Reference**: `inkarms --help`
- **Configuration**: `inkarms config --help`
- **Skill System**: `inkarms skill --help`

For issues or questions, check the audit logs:
```bash
tail -f ~/.inkarms/logs/audit.jsonl
```
