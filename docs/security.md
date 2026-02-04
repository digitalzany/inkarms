# Security & Sandbox

InkArms provides comprehensive security features to safely execute AI-generated commands and protect sensitive data.

## Overview

The security system consists of three main components:

1. **Command Filtering** - Whitelist/blacklist based command validation
2. **Sandbox Execution** - Safe command execution with restrictions
3. **Audit Logging** - Complete audit trail of all operations

## Command Filtering

### Modes

InkArms supports four security modes:

#### Whitelist Mode (Recommended)

Only explicitly allowed commands can execute:

```yaml
# ~/.inkarms/config.yaml
security:
  sandbox:
    enable: true
    mode: whitelist
  whitelist:
    - ls
    - cat
    - git
    - python
    - npm
```

Commands not in the whitelist are blocked:
```bash
$ inkarms run "list files"
# AI generates: ls -la ✓ (allowed)

$ inkarms run "delete everything"
# AI generates: rm -rf / ✗ (blocked)
```

#### Blacklist Mode

All commands except explicitly forbidden ones can execute:

```yaml
security:
  sandbox:
    mode: blacklist
  blacklist:
    - rm -rf
    - sudo
    - dd
    - curl | bash
```

#### Prompt Mode

All commands require user confirmation:

```yaml
security:
  sandbox:
    mode: prompt
```

Before each command executes, you'll be asked:
```
⚠️  About to execute: rm important_file.txt
   Allow? [y/N]:
```

#### Disabled Mode

No security filtering (not recommended):

```yaml
security:
  sandbox:
    mode: disabled
```

### Pattern Matching

Whitelist and blacklist support wildcards:

```yaml
whitelist:
  - git *          # Matches any git command
  - npm install *  # Matches npm install with any args
  - python *.py    # Matches running any .py file
```

Exact matches:
```yaml
whitelist:
  - ls             # Only "ls" without args
```

Regex-like patterns:
```yaml
blacklist:
  - rm.*-rf.*      # Blocks any rm with -rf flag
  - sudo.*         # Blocks all sudo commands
```

### Priority Rules

1. **Blacklist has priority**: If a command matches both whitelist and blacklist, it's blocked
2. **First match wins**: First matching pattern determines the result
3. **Base command check**: Only the first word (command) is checked for basic filtering

## Path Restrictions

Protect sensitive directories from access:

### Default Restrictions

By default, these paths are blocked:

- `~/.ssh` - SSH keys
- `~/.aws` - AWS credentials
- `~/.config/gcloud` - Google Cloud credentials
- `/etc` - System configuration
- `/root` - Root user directory
- `/var` - System data

### Custom Restrictions

Add your own restrictions:

```yaml
security:
  restricted_paths:
    no_access:
      - ~/.gnupg           # GPG keys
      - ~/.docker          # Docker configs
      - /private/secrets   # Custom secrets dir
    read_only:
      - /usr/local/config  # Allow read, block write
```

### How It Works

When a command contains file paths, they're checked against restrictions:

```bash
$ inkarms run "show my ssh config"
# AI generates: cat ~/.ssh/config
# ✗ Blocked: Access to ~/.ssh is restricted

$ inkarms run "list my documents"
# AI generates: ls ~/Documents
# ✓ Allowed: ~/Documents is not restricted
```

## Sandbox Execution

The sandbox executor provides safe command execution:

### Features

- **Command filtering** - Whitelist/blacklist enforcement
- **Path restrictions** - Block sensitive paths
- **Timeout enforcement** - Kill long-running commands
- **Environment isolation** - Control environment variables
- **Working directory** - Execute in specific directories
- **Output capture** - Safely capture stdout/stderr

### Timeout Configuration

Prevent runaway processes:

```python
# Default timeout: 30 seconds
result = sandbox.execute("long_running_command", timeout=60)
```

In practice, timeouts are automatic:
```bash
$ inkarms run "analyze this large dataset"
# AI generates: python analyze.py huge_file.csv
# Executes with 30s timeout
# If timeout: Command execution stopped
```

### Environment Variables

Control what environment is available:

```python
result = sandbox.execute(
    "python script.py",
    env={
        "API_KEY": "safe_key",
        "DEBUG": "true"
    }
)
```

## Audit Logging

Every operation is logged for security and compliance.

### Log Format

Logs use JSON Lines (.jsonl) format:

```jsonl
{"timestamp": "2026-02-02T10:30:00", "event_type": "command_start", "command": "ls -la"}
{"timestamp": "2026-02-02T10:30:01", "event_type": "command_complete", "command": "ls -la", "exit_code": 0}
{"timestamp": "2026-02-02T10:30:05", "event_type": "command_blocked", "command": "rm -rf /", "reason": "Not in whitelist"}
```

### Event Types

The following events are logged:

**Command Events:**
- `command_start` - Command execution started
- `command_complete` - Command finished successfully
- `command_blocked` - Command was blocked by security
- `command_error` - Command execution failed

**Query Events:**
- `query_start` - AI query started
- `query_complete` - AI query completed
- `query_error` - AI query failed

**Configuration:**
- `config_changed` - Configuration modified
- `secret_added` - Secret added to vault
- `secret_deleted` - Secret removed

**Skills:**
- `skill_installed` - Skill installed
- `skill_removed` - Skill removed
- `skill_loaded` - Skill loaded into session

**Sessions:**
- `session_start` - Session started
- `session_end` - Session ended with totals

### Configuration

```yaml
security:
  audit_log:
    enable: true
    path: ~/.inkarms/audit.jsonl

    # Rotation
    rotation: daily           # daily, weekly, or size
    max_size_mb: 100         # For size-based rotation
    retention_days: 90       # Keep logs for 90 days
    compress_old: true       # Gzip old logs

    # Privacy
    include_responses: false # Don't log AI responses
    include_queries: true    # Log user queries
    hash_queries: false      # Hash queries for privacy
    redact_paths: true       # Redact file paths

    # Performance
    buffer_size: 100         # Events before flush
    flush_interval_seconds: 5
```

### Privacy Options

#### Query Hashing

Hide sensitive queries while maintaining audit trail:

```yaml
hash_queries: true
```

Instead of:
```json
{"query": "What is my password for service X?"}
```

Logs:
```json
{"query": "a3b2c1d4e5f6..."}  # SHA256 hash
```

#### Response Filtering

Exclude AI responses from logs:

```yaml
include_responses: false
```

#### Path Redaction

Automatically redact file paths:

```yaml
redact_paths: true
```

```json
// Before:
{"command": "cat /home/user/.env"}

// After:
{"command": "cat [PATH]"}
```

#### Custom Redaction

Add your own redaction patterns:

```yaml
redact_patterns:
  - "password=\\w+"
  - "api_key=\\w+"
  - "\\b\\d{16}\\b"  # Credit card numbers
```

### Log Rotation

Logs automatically rotate to prevent unlimited growth:

**Daily Rotation:**
```yaml
rotation: daily
```
New log file each day: `audit_20260202.jsonl.gz`

**Size-based Rotation:**
```yaml
rotation: size
max_size_mb: 100
```
New log when current reaches 100MB

**Weekly Rotation:**
```yaml
rotation: weekly
```
New log each week

### Log Analysis

Parse logs with standard JSON tools:

```bash
# Count events by type
cat ~/.inkarms/audit.jsonl | jq -r .event_type | sort | uniq -c

# Find all blocked commands
cat ~/.inkarms/audit.jsonl | jq 'select(.event_type=="command_blocked")'

# Calculate total cost
cat ~/.inkarms/audit.jsonl | jq 'select(.cost) | .cost' | awk '{s+=$1} END {print s}'

# Commands in last hour
cat ~/.inkarms/audit.jsonl | jq 'select(.timestamp > "2026-02-02T09:00:00")'
```

## Best Practices

### 1. Use Whitelist Mode in Production

```yaml
security:
  sandbox:
    mode: whitelist
```

### 2. Minimal Whitelist

Only add commands you actually need:

```yaml
whitelist:
  - git
  - npm
  - python
  # Don't add: rm, dd, sudo, etc.
```

### 3. Expand Blacklist

Block dangerous patterns:

```yaml
blacklist:
  - rm -rf
  - sudo
  - dd
  - curl | bash
  - wget | bash
  - chmod 777
  - eval
```

### 4. Restrict Sensitive Paths

```yaml
restricted_paths:
  no_access:
    - ~/.ssh
    - ~/.aws
    - ~/.gnupg
    - ~/.kube
    - ~/.docker
```

### 5. Enable Audit Logging

```yaml
audit_log:
  enable: true
  retention_days: 90
  compress_old: true
```

### 6. Review Logs Regularly

```bash
# Weekly audit
inkarms audit search --last-week

# Check for blocked commands
inkarms audit search --type command_blocked
```

### 7. Use Query Hashing for Sensitive Work

```yaml
hash_queries: true
include_responses: false
```

## Configuration Reference

Complete security configuration:

```yaml
security:
  # Sandbox settings
  sandbox:
    enable: true
    mode: whitelist  # whitelist, blacklist, prompt, disabled

  # Command whitelist
  whitelist:
    - ls
    - cat
    - git
    - python
    - npm
    - node

  # Command blacklist
  blacklist:
    - rm -rf
    - sudo
    - dd
    - curl | bash
    - wget | bash

  # Path restrictions
  restricted_paths:
    no_access:
      - ~/.ssh
      - ~/.aws
      - ~/.config/gcloud
    read_only: []

  # Audit logging
  audit_log:
    enable: true
    path: ~/.inkarms/audit.jsonl
    rotation: daily
    max_size_mb: 100
    retention_days: 90
    compress_old: true
    include_responses: false
    include_queries: true
    hash_queries: false
    redact_paths: true
    redact_patterns: []
    buffer_size: 100
    flush_interval_seconds: 5
```

## Troubleshooting

### Command Blocked Unexpectedly

Check if it matches a blacklist pattern:
```bash
inkarms config show security.blacklist
```

Add to whitelist if safe:
```bash
inkarms config set security.whitelist.+ "safe_command"
```

### Path Access Denied

Check restricted paths:
```bash
inkarms config show security.restricted_paths
```

Remove restriction if needed:
```bash
inkarms config set security.restricted_paths.no_access.- "~/.path"
```

### Logs Growing Too Large

Adjust rotation settings:
```bash
inkarms config set security.audit_log.max_size_mb 50
inkarms config set security.audit_log.retention_days 30
```

### Slow Performance

Increase buffer size:
```bash
inkarms config set security.audit_log.buffer_size 500
```

## See Also

- [Configuration Reference](configuration.md) - Full config documentation
- [User Guide](user_guide.md) - Getting started
- [CLI Reference](cli_reference.md) - Command reference
