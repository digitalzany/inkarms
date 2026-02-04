# Advanced Tool Use

This guide covers InkArms' advanced tool capabilities including HTTP requests, Python code execution, Git operations, real-time streaming, parallel execution, and usage analytics.

## Table of Contents

1. [Overview](#overview)
2. [Built-in Tools](#built-in-tools)
   - [HTTP Request Tool](#http-request-tool)
   - [Python Eval Tool](#python-eval-tool)
   - [Git Operations Tool](#git-operations-tool)
3. [Tool Configuration](#tool-configuration)
4. [Tool Approval Modes](#tool-approval-modes)
5. [Streaming Events](#streaming-events)
6. [Parallel Execution](#parallel-execution)
7. [Tool Metrics](#tool-metrics)
8. [Examples](#examples)
9. [Security Considerations](#security-considerations)
10. [Troubleshooting](#troubleshooting)

## Overview

InkArms provides a comprehensive tool system that allows the AI assistant to:
- Make HTTP API requests
- Execute safe Python code
- Perform Git operations
- Execute bash commands (with sandbox)
- Read and write files
- Search and list files

All tools support:
- **Real-time streaming events** - See tool execution progress in real-time
- **Parallel execution** - Multiple tools run concurrently for better performance
- **Usage metrics** - Track tool usage, timing, and success rates
- **Security sandbox** - All operations are sandboxed and audited

## Built-in Tools

### HTTP Request Tool

Make HTTP requests to web APIs with full control over methods, headers, and authentication.

**Capabilities:**
- All HTTP methods: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS
- Authentication: Bearer tokens, Basic auth
- Custom headers and query parameters
- JSON and text request/response bodies
- Automatic redirect following
- Configurable timeouts (default 30s, max 120s)

**Example Usage:**

```bash
# CLI - Make a GitHub API request
inkarms run "Get the latest release info for python/cpython from GitHub API" --tools --tool-approval auto

# The AI will use the http_request tool:
# {
#     "tool": "http_request",
#     "url": "https://api.github.com/repos/python/cpython/releases/latest",
#     "method": "GET",
#     "headers": {"Accept": "application/json"}
# }
```

**Configuration:**

```yaml
# ~/.inkarms/config.yaml
agent:
  enable_tools: true
  allowed_tools:
    - http_request
  # OR block specific tools
  blocked_tools: []
```

**Security Notes:**
- HTTP requests are considered **dangerous tools** (require approval in manual mode)
- Requests go through security sandbox
- All requests are logged in audit trail
- Supports HTTPS only (HTTP auto-upgraded)

### Python Eval Tool

Execute Python code safely using RestrictedPython for calculations, data processing, and logic.

**Capabilities:**
- Safe code execution with sandboxing
- Whitelisted modules: math, datetime, json, re, random, string, itertools, functools, collections
- Print output capture
- Support for functions, classes, and comprehensions
- Configurable timeout (default 30s, max 60s)
- Syntax and runtime error handling

**Example Usage:**

```bash
# CLI - Calculate factorial and explain
inkarms run "Calculate 15! (factorial) and show the result" --tools --tool-approval auto

# The AI will use the python_eval tool:
# {
#     "tool": "python_eval",
#     "code": "import math\nresult = math.factorial(15)\nprint(f'15! = {result}')"
# }
```

**Whitelisted Modules:**

```python
# Safe imports allowed
import math          # Mathematical functions
import datetime      # Date and time
import json          # JSON encoding/decoding
import re            # Regular expressions
import random        # Random number generation
import string        # String operations
import itertools     # Iterator tools
import functools     # Functional programming
import collections   # Container datatypes
```

**Example Code:**

```python
# Mathematical calculations
import math
print(math.sqrt(256))
print(math.pi)

# Date operations
from datetime import datetime, timedelta
now = datetime.now()
tomorrow = now + timedelta(days=1)
print(f"Tomorrow: {tomorrow.strftime('%Y-%m-%d')}")

# Data processing
import json
data = {"name": "Alice", "age": 30}
print(json.dumps(data, indent=2))

# Functions and classes
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

print(fibonacci(10))

# List comprehensions
squares = [x**2 for x in range(10)]
print(squares)
```

**Known Limitations:**

1. **CPU-bound timeout**: Infinite loops that don't yield to the event loop cannot be timed out
   ```python
   # This CANNOT be stopped:
   while True:
       x = 1  # CPU-bound loop
   ```

2. **Augmented assignment on attributes**: Not allowed by RestrictedPython
   ```python
   # NOT allowed:
   self.count += 1

   # Use instead:
   self.count = self.count + 1
   ```

3. **Import restrictions**: Only whitelisted modules can be imported
   ```python
   # NOT allowed:
   import os
   import sys
   import requests
   ```

**Security Notes:**
- Python eval is **dangerous** (requires approval in manual mode)
- All code goes through RestrictedPython compiler
- Execution happens in restricted environment
- Print output limited to prevent memory issues
- All executions logged in audit trail

### Git Operations Tool

Perform Git version control operations on repositories.

**Available Operations:**

| Operation | Description | Example Input |
|-----------|-------------|---------------|
| `status` | Show working tree status | `{"operation": "status", "repo_path": "."}` |
| `log` | Display commit history | `{"operation": "log", "repo_path": ".", "limit": 10}` |
| `diff` | Show file changes | `{"operation": "diff", "repo_path": ".", "file_path": "README.md"}` |
| `add` | Stage files for commit | `{"operation": "add", "repo_path": ".", "files": ["file.py"]}` |
| `commit` | Create a commit | `{"operation": "commit", "repo_path": ".", "message": "Fix bug"}` |
| `branch` | List or create branches | `{"operation": "branch", "repo_path": ".", "create": "feature"}` |
| `checkout` | Switch branches | `{"operation": "checkout", "repo_path": ".", "branch": "main"}` |

**Example Usage:**

```bash
# CLI - Check repository status
inkarms run "What's the current git status and recent commits?" --tools --tool-approval auto

# The AI will use multiple git operations:
# 1. git_operation(operation="status", repo_path=".")
# 2. git_operation(operation="log", repo_path=".", limit=5)
```

**Security Notes:**
- Git operations are **dangerous** (modify repository state)
- Only works on valid Git repositories
- Uses system Git configuration (SSH keys, credentials)
- Advanced operations (merge, rebase, push) not exposed for safety
- All operations logged in audit trail

## Tool Configuration

Configure tool behavior in `~/.inkarms/config.yaml`:

```yaml
agent:
  # Enable/disable all tools
  enable_tools: true

  # Tool approval mode (auto, manual, disabled)
  tool_approval_mode: auto

  # Maximum iterations for multi-turn tool use
  max_iterations: 10

  # Timeout per iteration (seconds)
  timeout_per_iteration: 120

  # Whitelist specific tools (empty = all allowed)
  allowed_tools: []

  # Blacklist specific tools
  blocked_tools:
    - execute_bash  # Block bash execution

  # Per-tool settings (optional)
  tool_settings:
    http_request:
      default_timeout: 30
      max_timeout: 120
    python_eval:
      default_timeout: 30
      max_timeout: 60
```

## Tool Approval Modes

InkArms supports three approval modes for tool execution:

### Auto Mode (Recommended for Trusted Users)

All tools execute automatically without prompts.

```yaml
agent:
  tool_approval_mode: auto
```

```bash
# CLI with auto approval
inkarms run "Calculate 15!" --tools --tool-approval auto
```

**Use when:**
- You trust the AI to make safe decisions
- You want fast, uninterrupted workflow
- You have tool restrictions configured

### Manual Mode (Recommended for Production)

Dangerous tools require user approval before execution.

```yaml
agent:
  tool_approval_mode: manual
```

```bash
# CLI with manual approval (prompts for dangerous tools)
inkarms run "Make a request to example.com" --tools --tool-approval manual
```

**Approval Prompt:**
```
⚠️  Tool Approval Required

Tool: http_request
Input: {
  "url": "https://example.com",
  "method": "GET"
}

This tool can:
- Make network requests to external servers
- Send data to third parties
- Consume API quotas

Approve execution? [y/N]:
```

**Use when:**
- Running in production environments
- Executing unfamiliar queries
- Working with sensitive data
- Want explicit control over operations

### Disabled Mode

Tools are completely disabled (AI responds without tools).

```yaml
agent:
  tool_approval_mode: disabled
```

```bash
# CLI with tools disabled
inkarms run "What's 2+2?" --tools --tool-approval disabled
```

## Streaming Events

InkArms provides real-time streaming events during tool execution, allowing you to see progress as it happens.

**Event Types:**

| Event Type | Description | When Emitted |
|------------|-------------|--------------|
| `ITERATION_START` | Agent iteration begins | Start of each iteration |
| `ITERATION_END` | Agent iteration completes | End of each iteration |
| `TOOL_START` | Tool execution starts | Before tool runs |
| `TOOL_COMPLETE` | Tool execution succeeds | After successful tool execution |
| `TOOL_ERROR` | Tool execution fails | After tool error |
| `TOOL_APPROVAL_NEEDED` | Tool needs approval | When manual approval required |
| `TOOL_APPROVED` | Tool approved by user | After user approves |
| `TOOL_DENIED` | Tool denied by user | After user denies |
| `AI_RESPONSE` | AI response received | After AI completion |
| `AGENT_COMPLETE` | Agent loop completes | Final completion |

**Programmatic Usage:**

```python
import asyncio
from inkarms.agent import AgentLoop, AgentConfig, AgentEvent, EventType
from inkarms.config import get_config
from inkarms.providers import get_provider_manager
from inkarms.security.sandbox import SandboxExecutor
from inkarms.tools.builtin import register_builtin_tools
from inkarms.tools.registry import ToolRegistry

def event_handler(event: AgentEvent):
    """Handle streaming events."""
    if event.event_type == EventType.TOOL_START:
        print(f"⚙️  Executing: {event.tool_name}")
    elif event.event_type == EventType.TOOL_COMPLETE:
        execution_time = event.data.get("execution_time", 0)
        print(f"✅ Completed: {event.tool_name} ({execution_time:.2f}s)")
    elif event.event_type == EventType.TOOL_ERROR:
        error = event.data.get("error", "Unknown")
        print(f"❌ Failed: {event.tool_name} - {error}")

async def main():
    config = get_config()
    provider = get_provider_manager()
    sandbox = SandboxExecutor.from_config(config.security)

    # Setup tools
    registry = ToolRegistry()
    register_builtin_tools(registry, sandbox)

    # Create agent with event callback
    agent = AgentLoop(
        provider_manager=provider,
        tool_registry=registry,
        event_callback=event_handler,  # Real-time events
    )

    # Run with streaming
    messages = [{"role": "user", "content": "Calculate sqrt(256) and check git status"}]
    result = await agent.run(messages)

    print(f"Final: {result.final_response}")
    print(f"Tools used: {len(result.tool_calls_made)}")

asyncio.run(main())
```

**Platform Integration:**

Messaging platforms (Telegram, Slack, Discord) use event callbacks to show real-time progress:

```python
from inkarms.platforms.processor import MessageProcessor

def telegram_event_handler(event: AgentEvent):
    """Update Telegram message with progress."""
    if event.event_type == EventType.TOOL_START:
        telegram.edit_message(f"⚙️ Executing: {event.tool_name}...")
    elif event.event_type == EventType.TOOL_COMPLETE:
        telegram.edit_message(f"✅ Completed: {event.tool_name}")

# Create processor with event callback
processor = MessageProcessor(event_callback=telegram_event_handler)

# Events are emitted in real-time during processing
result = await processor.process(query, ...)
```

See [`examples/platform_tool_streaming.py`](../examples/platform_tool_streaming.py) for a complete example.

## Parallel Execution

InkArms automatically executes multiple independent tools concurrently for better performance.

**How It Works:**

When the AI requests multiple tools in a single response, they are executed in parallel using `asyncio.gather()`:

```python
# Sequential (old approach): 3.0s total
result1 = await tool1.execute()  # 1.0s
result2 = await tool2.execute()  # 1.0s
result3 = await tool3.execute()  # 1.0s

# Parallel (InkArms): 1.0s total
results = await asyncio.gather(
    tool1.execute(),  # All run
    tool2.execute(),  # concurrently
    tool3.execute(),  # (1.0s total)
)
```

**Performance Benefits:**

| Scenario | Sequential | Parallel | Speedup |
|----------|------------|----------|---------|
| 3 file reads (0.05s each) | 0.15s | 0.05s | 3x |
| 3 HTTP requests (1.0s each) | 3.0s | 1.0s | 3x |
| Mixed I/O operations | 5.0s | 1.5s | 3.3x |

**Example:**

```bash
# Query requiring multiple tools
inkarms run "List files, check git status, and calculate sqrt(144)" --tools --tool-approval auto

# InkArms executes all 3 tools in parallel:
# ├─ list_files() ────┐
# ├─ git_operation() ─┼─> All complete in ~1s
# └─ python_eval() ───┘
```

**No Configuration Required:**

Parallel execution is automatic and transparent. The agent loop handles:
- Concurrent execution with `asyncio.gather()`
- Error isolation (one tool failure doesn't block others)
- Result ordering (matches request order)
- Event emission (all events captured)

## Tool Metrics

InkArms tracks comprehensive metrics for all tool executions.

**Tracked Metrics:**

- Total executions per tool
- Success/failure counts
- Execution time (total and average)
- Success rate percentage
- Last used timestamp
- Recent execution history

**Viewing Metrics:**

```bash
# View all metrics
inkarms tools metrics

# View specific tool
inkarms tools metrics http_request

# Clear all metrics
inkarms tools metrics --clear
```

**Example Output:**

```
Tool Usage Metrics

Total Executions: 247
Overall Success Rate: 94.3%

Most Used Tools:
  1. read_file: 89 times
  2. python_eval: 62 times
  3. list_files: 41 times
  4. http_request: 28 times
  5. git_operation: 27 times

All Tools:

┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Tool           ┃ Executions  ┃ Success Rate ┃ Avg Time ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ read_file      │ 89          │ 98.9%        │ 0.042s   │
│ python_eval    │ 62          │ 91.9%        │ 0.087s   │
│ list_files     │ 41          │ 100.0%       │ 0.053s   │
│ http_request   │ 28          │ 89.3%        │ 1.234s   │
│ git_operation  │ 27          │ 92.6%        │ 0.168s   │
└────────────────┴─────────────┴──────────────┴──────────┘

Recent Executions:

✓ python_eval - 0.089s (14:32:15)
✓ http_request - 1.456s (14:32:10)
✗ git_operation - 0.034s (14:31:58)
✓ read_file - 0.038s (14:31:45)
✓ list_files - 0.052s (14:31:40)
```

**Programmatic Access:**

```python
from inkarms.tools.metrics import get_metrics_tracker

metrics = get_metrics_tracker()

# Get stats for specific tool
stats = metrics.get_tool_stats("http_request")
print(f"Success rate: {stats.success_rate * 100}%")
print(f"Average time: {stats.average_execution_time:.3f}s")

# Get most used tools
most_used = metrics.get_most_used_tools(limit=5)
for tool_name, count in most_used:
    print(f"{tool_name}: {count} times")

# Get recent executions
recent = metrics.get_recent_executions(limit=10)
for exec in recent:
    status = "✓" if exec.success else "✗"
    print(f"{status} {exec.tool_name} - {exec.execution_time:.3f}s")
```

**Storage:**

Metrics are stored in `~/.inkarms/tool_metrics.json`:

```json
{
  "metrics": [
    {
      "tool_name": "python_eval",
      "success": true,
      "execution_time": 0.089,
      "timestamp": 1704470535.123,
      "error_message": null
    },
    ...
  ],
  "last_updated": 1704470535.456
}
```

## Examples

### Example 1: API Integration

```bash
inkarms run "Get the weather forecast for San Francisco from wttr.in API" --tools --tool-approval auto
```

**Tool Execution:**
```json
{
  "tool": "http_request",
  "url": "https://wttr.in/San Francisco?format=j1",
  "method": "GET"
}
```

### Example 2: Data Processing

```bash
inkarms run "Calculate the first 10 Fibonacci numbers and format as JSON" --tools --tool-approval auto
```

**Tool Execution:**
```json
{
  "tool": "python_eval",
  "code": "import json\ndef fib(n):\n    a, b = 0, 1\n    result = []\n    for _ in range(n):\n        result.append(a)\n        a, b = b, a + b\n    return result\n\nfibonacci = fib(10)\nprint(json.dumps(fibonacci, indent=2))"
}
```

### Example 3: Repository Analysis

```bash
inkarms run "Analyze this git repository: show status, recent commits, and file count" --tools --tool-approval auto
```

**Tool Execution (parallel):**
```json
[
  {"tool": "git_operation", "operation": "status", "repo_path": "."},
  {"tool": "git_operation", "operation": "log", "repo_path": ".", "limit": 5},
  {"tool": "execute_bash", "command": "find . -type f | wc -l"}
]
```

### Example 4: Complex Workflow

```bash
inkarms run "Fetch GitHub API rate limit, calculate time until reset, and save as JSON file" --tools --tool-approval auto
```

**Tool Execution (sequential with dependencies):**
```json
[
  {
    "tool": "http_request",
    "url": "https://api.github.com/rate_limit",
    "method": "GET"
  },
  {
    "tool": "python_eval",
    "code": "from datetime import datetime\nimport json\n# Process rate limit data\n..."
  },
  {
    "tool": "write_file",
    "path": "rate_limit.json",
    "content": "..."
  }
]
```

## Security Considerations

### Dangerous Tools

The following tools are considered dangerous and require approval in manual mode:

- `http_request` - Can make external network requests
- `python_eval` - Can execute arbitrary code
- `execute_bash` - Can run shell commands
- `write_file` - Can modify filesystem
- `git_operation` (add, commit, checkout) - Can modify repository state

### Security Features

1. **Sandbox Execution**: All tools run in security sandbox with:
   - Command filtering (whitelist/blacklist)
   - Path restrictions (block ~/.ssh, ~/.aws, etc.)
   - Timeout enforcement
   - Resource limits

2. **Audit Logging**: All tool executions logged to `~/.inkarms/audit.jsonl`:
   ```json
   {
     "timestamp": "2024-01-05T14:32:15.123Z",
     "event_type": "tool_execution",
     "tool_name": "http_request",
     "success": true,
     "execution_time": 1.234,
     "metadata": {"url": "https://api.example.com"}
   }
   ```

3. **RestrictedPython**: Python eval uses RestrictedPython for:
   - Import restrictions (whitelist only)
   - Attribute access control
   - Safe builtins only
   - No filesystem access

4. **Tool Restrictions**: Configure allowed/blocked tools:
   ```yaml
   agent:
     allowed_tools:
       - read_file
       - list_files
       - python_eval  # Allow only safe calculations
     blocked_tools:
       - execute_bash  # Block shell access
       - write_file    # Block file writes
   ```

### Best Practices

1. **Use manual approval mode** in production environments
2. **Restrict tools** to minimum required set
3. **Review audit logs** regularly for suspicious activity
4. **Set timeouts** to prevent resource exhaustion
5. **Whitelist specific domains** for HTTP requests (future feature)
6. **Monitor metrics** for unusual patterns

## Troubleshooting

### Tools Not Executing

**Problem**: AI doesn't use tools even when appropriate.

**Solutions:**
```yaml
# 1. Ensure tools are enabled
agent:
  enable_tools: true

# 2. Check approval mode
agent:
  tool_approval_mode: auto  # or manual

# 3. Verify tools not blocked
agent:
  blocked_tools: []  # Empty list

# 4. Check allowed_tools (empty = all allowed)
agent:
  allowed_tools: []
```

### Python Eval Timeout

**Problem**: Python code times out.

**Solutions:**
```yaml
# Increase timeout
agent:
  tool_settings:
    python_eval:
      max_timeout: 60  # seconds
```

**Avoid CPU-bound infinite loops** (cannot be timed out):
```python
# BAD - Cannot be stopped
while True:
    x = 1

# GOOD - Use finite iterations
for i in range(1000):
    x = i
```

### HTTP Request Errors

**Problem**: HTTP requests fail or timeout.

**Solutions:**
```yaml
# Increase timeout
agent:
  tool_settings:
    http_request:
      max_timeout: 120  # seconds
```

**Check common issues:**
- URL is HTTPS (HTTP auto-upgraded)
- API requires authentication (provide headers)
- Rate limiting (check API quota)
- Network connectivity

### Git Operation Fails

**Problem**: Git operations fail with "not a git repository".

**Solution**: Ensure you're in a Git repository:
```bash
# Check if in git repo
git status

# Initialize if needed
git init
```

### Tool Metrics Not Saving

**Problem**: Metrics are lost between sessions.

**Solution**: Check permissions on data directory:
```bash
# Ensure directory exists and is writable
ls -la ~/.inkarms/
chmod 755 ~/.inkarms/

# Check metrics file
cat ~/.inkarms/tool_metrics.json
```

### Import Error in Python Eval

**Problem**: `ModuleNotFoundError: No module named 'requests'`

**Solution**: Only whitelisted modules are available. Use http_request tool instead:

```python
# NOT ALLOWED:
import requests
response = requests.get("https://api.example.com")

# USE INSTEAD:
# Tell the AI: "Make an HTTP request to https://api.example.com"
# AI will use http_request tool
```

## See Also

- [Configuration Guide](configuration.md) - Tool configuration reference
- [Security Guide](security.md) - Security sandbox and audit logging
- [CLI Reference](cli_reference.md) - Command-line tool usage
- [Examples](../examples/) - Complete code examples
- [API Documentation](../README.md) - Python API reference

## Feedback

Found a bug or have a feature request? Please [open an issue](https://github.com/inkarms/inkarms/issues).
