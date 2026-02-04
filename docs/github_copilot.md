# GitHub Copilot Integration

InkArms supports GitHub Copilot as an AI provider using OAuth device flow authentication.

## Requirements

- **GitHub Account** with GitHub Copilot subscription
- **Active Copilot Access** - Personal, Business, or Enterprise plan

## Quick Start

### 1. Configure GitHub Copilot

Use the QuickStart wizard:

```bash
inkarms config init
```

Select "GitHub Copilot" as your provider, then choose a model:
- **GPT-5.2** (Latest, Recommended) - Latest stable version
- **GPT-5.2-Codex** (Latest, Code-focused) - Code optimization
- **Claude Sonnet 4.5** (Balanced) - Fast and capable
- **Claude Opus 4.5** (Most capable) - Advanced reasoning
- **Gemini 2.5 Pro** (Multimodal) - Vision and reasoning

### 2. First-Time Authentication

On your first request, InkArms will automatically initiate OAuth device flow:

```bash
inkarms run "Hello!"
```

You'll see output like:

```
GitHub Copilot Authentication Required
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Visit: https://github.com/login/device
Enter code: XXXX-XXXX

Waiting for authorization...
```

**Steps:**
1. Visit https://github.com/login/device in your browser
2. Enter the displayed code
3. Click "Authorize" to grant access
4. Return to terminal - authentication will complete automatically

### 3. Credentials Stored Automatically

After successful authentication:
- Credentials are saved locally (managed by LiteLLM)
- No need to re-authenticate for future requests
- Tokens automatically refreshed as needed

## Available Models

GitHub Copilot provides access to models from multiple providers through a unified interface.

### OpenAI Models

**Latest (Recommended):**
```bash
# GPT-5.2 - Latest stable version
inkarms run "Explain quantum computing" --model github_copilot/gpt-5.2

# GPT-5.2-Codex - Latest code-focused
inkarms run "Write a sorting algorithm" --model github_copilot/gpt-5.2-codex
```

**GPT-5.1 Series:**
```bash
github_copilot/gpt-5.1              # Enhanced version
github_copilot/gpt-5.1-codex        # Code-optimized
github_copilot/gpt-5.1-codex-mini   # Lightweight (preview)
github_copilot/gpt-5.1-codex-max    # High-capacity
```

**GPT-5 Series (Closing 2026-02-17):**
```bash
github_copilot/gpt-5                # Original GPT-5
github_copilot/gpt-5-mini           # Lightweight
github_copilot/gpt-5-codex          # Code-focused
```

**GPT-4 Series:**
```bash
github_copilot/gpt-4.1              # General availability
```

### Anthropic Claude Models

```bash
# Claude Sonnet 4.5 - Balanced performance (Recommended)
inkarms run "Analyze this code" --model github_copilot/claude-sonnet-4.5

# Claude Opus 4.5 - Most capable reasoning
inkarms run "Complex task" --model github_copilot/claude-opus-4.5

# Claude Haiku 4.5 - Fast and efficient
inkarms run "Quick question" --model github_copilot/claude-haiku-4.5

# Claude Sonnet 4 - Previous generation
inkarms run "query" --model github_copilot/claude-sonnet-4

# Claude Opus 4.1 - Previous generation (Closing 2026-02-17)
inkarms run "query" --model github_copilot/claude-opus-4.1
```

### Google Gemini Models

```bash
# Gemini 2.5 Pro - Multimodal capabilities
inkarms run "Describe this image" --model github_copilot/gemini-2.5-pro

# Gemini 3 Flash - Fast processing (Preview)
inkarms run "Quick task" --model github_copilot/gemini-3-flash

# Gemini 3 Pro - Advanced reasoning (Preview)
inkarms run "Complex analysis" --model github_copilot/gemini-3-pro
```

### Other Models

```bash
# Grok Code Fast 1 (xAI) - Complimentary access
inkarms run "Code question" --model github_copilot/grok-code-fast-1

# Raptor mini - Fine-tuned GPT-5 mini (Preview)
inkarms run "query" --model github_copilot/raptor-mini
```

### Model Selection Guide

| Use Case | Recommended Model | Alternative |
|----------|------------------|-------------|
| **General tasks** | `gpt-5.2` | `claude-sonnet-4.5` |
| **Code generation** | `gpt-5.2-codex` | `gpt-5.1-codex-max` |
| **Complex reasoning** | `claude-opus-4.5` | `gemini-3-pro` |
| **Fast responses** | `claude-haiku-4.5` | `gpt-5.1-codex-mini` |
| **Multimodal** | `gemini-2.5-pro` | `gemini-3-flash` |
| **Cost-effective** | `gpt-5.1-codex-mini` | `claude-haiku-4.5` |

### Model Naming Convention

All GitHub Copilot models use the prefix `github_copilot/`:

```
github_copilot/<model-name>
```

Examples:
- OpenAI: `github_copilot/gpt-5.2`
- Anthropic: `github_copilot/claude-sonnet-4.5`
- Google: `github_copilot/gemini-2.5-pro`
- xAI: `github_copilot/grok-code-fast-1`

### Important Notes

- **Sunset Dates**: Some models are being phased out (GPT-5, GPT-5-Codex, Claude Opus 4.1 closing 2026-02-17)
- **Preview Models**: Gemini 3 series and some variants are in public preview
- **Availability**: Model access may vary by subscription tier (Individual/Business/Enterprise)
- **Multipliers**: Different models have different cost multipliers on paid plans
- **Content Filters**: All models include filters for harmful content and public code matching
- **Complete List**: See [GitHub Copilot Supported Models](https://docs.github.com/en/copilot/reference/ai-models/supported-models) for the latest model catalog

## Configuration

### Basic Configuration

After running the wizard, your `~/.inkarms/config.yaml` will contain:

```yaml
providers:
  default: github_copilot/gpt-4
  timeout: 120
  max_retries: 3
```

### Advanced Configuration

For custom token storage location:

```bash
# Set environment variables (optional)
export GITHUB_COPILOT_TOKEN_DIR=~/.inkarms/copilot-tokens
export GITHUB_COPILOT_ACCESS_TOKEN_FILE=access_token.json
export GITHUB_COPILOT_API_KEY_FILE=api_key.json
```

Add to `~/.inkarms/config.yaml`:

```yaml
providers:
  default: github_copilot/gpt-4
  github_copilot:
    token_dir: ~/.inkarms/copilot-tokens
    access_token_file: access_token.json
    api_key_file: api_key.json
```

### Model Aliases

Create shortcuts for frequently used models:

```yaml
providers:
  default: copilot  # Use alias
  aliases:
    # Latest models (Recommended)
    copilot: github_copilot/gpt-5.2
    copilot-code: github_copilot/gpt-5.2-codex

    # Claude models
    copilot-sonnet: github_copilot/claude-sonnet-4.5
    copilot-opus: github_copilot/claude-opus-4.5
    copilot-haiku: github_copilot/claude-haiku-4.5

    # Gemini models
    copilot-gemini: github_copilot/gemini-2.5-pro

    # Specialized
    copilot-mini: github_copilot/gpt-5.1-codex-mini
    copilot-max: github_copilot/gpt-5.1-codex-max
```

Usage:

```bash
inkarms run "query" --model copilot
inkarms run "write code" --model copilot-code
inkarms run "complex task" --model copilot-opus
```

## Editor Integration Headers

For enhanced integration (advanced users), you can set editor-specific headers:

```python
# Python SDK usage
from litellm import completion

response = completion(
    model="github_copilot/gpt-4",
    messages=[{"role": "user", "content": "Your prompt"}],
    extra_headers={
        "editor-version": "vscode/1.85.1",
        "Copilot-Integration-Id": "inkarms",
        "editor-plugin-version": "0.7.0"
    }
)
```

## Troubleshooting

### Authentication Fails

**Problem:** Device flow times out or fails

**Solutions:**
1. Check GitHub Copilot subscription is active
2. Ensure you're logged into the correct GitHub account
3. Try re-authenticating:
   ```bash
   # Remove stored credentials
   rm -rf ~/.litellm_cache/github_copilot

   # Re-authenticate on next request
   inkarms run "test"
   ```

### Invalid Token Errors

**Problem:** `401 Unauthorized` or `403 Forbidden` errors

**Solutions:**
1. Verify Copilot subscription is active
2. Re-authenticate (remove cached tokens)
3. Check your GitHub account at https://github.com/settings/copilot

### Model Not Found

**Problem:** `Model 'github_copilot/...' not found`

**Solutions:**
1. Ensure LiteLLM is up to date:
   ```bash
   pip install --upgrade litellm
   ```
2. Verify model name is correct:
   - `github_copilot/gpt-4` ✓
   - `github-copilot/gpt-4` ✗ (wrong separator)
   - `copilot/gpt-4` ✗ (missing prefix)

### Rate Limiting

**Problem:** Too many requests errors

**Solutions:**
1. GitHub Copilot has usage limits based on your plan
2. Add retry configuration:
   ```yaml
   providers:
     max_retries: 5
     timeout: 180
   ```

## Comparison with Other Providers

| Feature | Anthropic | OpenAI | GitHub Copilot |
|---------|-----------|--------|----------------|
| **Authentication** | API Key | API Key | OAuth Device Flow |
| **Setup** | Manual key | Manual key | Automatic |
| **Cost** | Pay-per-use | Pay-per-use | Subscription-based |
| **Models** | Claude 4 | GPT-4, GPT-5, o3 | GPT-5.2, Claude, Gemini, Grok |
| **Providers** | Anthropic only | OpenAI only | Multi-provider access |
| **Best For** | General AI | General AI | Code & Development |

## Security Notes

- **OAuth Tokens**: Stored locally by LiteLLM (not InkArms)
- **Token Location**: `~/.litellm_cache/github_copilot/` by default
- **Encryption**: LiteLLM handles token security
- **Scopes**: Limited to Copilot API access only
- **Revocation**: Revoke access at https://github.com/settings/applications

## Cost Tracking

GitHub Copilot operates on a subscription model:

- **Individual**: ~$10/month
- **Business**: ~$19/user/month
- **Enterprise**: Custom pricing

InkArms' cost tracking will show token usage but not actual costs (since you pay a flat subscription fee).

## References

- [GitHub Copilot Documentation](https://docs.github.com/en/copilot)
- [GitHub Copilot Supported Models](https://docs.github.com/en/copilot/reference/ai-models/supported-models) - Official model catalog
- [LiteLLM GitHub Copilot Provider](https://docs.litellm.ai/docs/providers/github_copilot)
- [OAuth Device Flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow)

## See Also

- [Configuration Guide](configuration.md) - Full configuration reference
- [Provider Guide](providers.md) - Other AI providers
- [User Guide](user_guide.md) - General InkArms usage

---

**Sources:**
- [GitHub Copilot | liteLLM](https://docs.litellm.ai/docs/providers/github_copilot)
- [Authentication Methods | github/copilot-cli](https://deepwiki.com/github/copilot-cli/4.1-authentication-methods)
- [OAuth Token Setup | dcai/github-copilot-proxy](https://deepwiki.com/dcai/github-copilot-proxy/2.1-oauth-token-setup)
