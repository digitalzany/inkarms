# Skill Authoring Guide

Welcome, skill crafter! This guide will teach you how to create skills that give InkArms new superpowers.

## What Are Skills?

Skills are portable instruction sets that teach InkArms how to handle specific tasks. They're like giving an octopus a new trick — but instead of juggling, it's reviewing code or generating documentation.

A skill consists of:
- **SKILL.md** — Natural language instructions for the AI
- **skill.yaml** — Metadata, keywords, and permissions

## Quick Start: Create Your First Skill

```bash
# Create a new skill
inkarms skill create my-awesome-skill

# This creates:
# ~/.inkarms/skills/my-awesome-skill/
# ├── SKILL.md
# └── skill.yaml
```

Edit the generated files:

```markdown
# SKILL.md
---
name: my-awesome-skill
description: Does awesome things
---

# My Awesome Skill

This skill helps with doing awesome things.

## When to Use

- When you need to do something awesome
- When regular methods just won't cut it

## Instructions

1. First, analyze the input
2. Then, apply awesomeness
3. Finally, deliver results in style

## Output Format

Return results as:
- A brief summary
- Detailed findings
- Recommendations
```

```yaml
# skill.yaml
name: my-awesome-skill
version: 1.0.0
description: Does awesome things

keywords:
  - awesome
  - amazing
  - fantastic

permissions:
  tools:
    - file_read
  network: false
  filesystem:
    read:
      - "*.py"
      - "*.js"
    write: []
```

## Skill Structure

### Directory Layout

```
skill-name/
├── SKILL.md           # Required: Instructions for the AI
├── skill.yaml         # Required: Metadata and permissions
├── templates/         # Optional: Template files
│   └── report.md
├── scripts/           # Optional: Helper scripts
│   └── analyze.py
├── references/        # Optional: Reference documents
│   └── standards.md
└── examples/          # Optional: Usage examples
    └── example-input.txt
```

### SKILL.md Format

The SKILL.md file contains instructions for the AI:

```markdown
---
name: security-scan
description: Identifies security vulnerabilities in code
---

# Security Scan Skill

This skill guides security analysis of code.

## When to Use

- Reviewing code for security issues
- Analyzing pull requests
- Checking for OWASP Top 10 vulnerabilities

## Instructions

When analyzing code for security:

### 1. Input Validation
- Check for SQL injection vulnerabilities
- Look for XSS (Cross-Site Scripting) risks
- Identify command injection possibilities

### 2. Authentication & Authorization
- Verify proper authentication checks
- Ensure authorization is enforced
- Check for hardcoded credentials

### 3. Data Protection
- Look for sensitive data exposure
- Check encryption usage
- Verify secure storage practices

## Output Format

Provide findings in this format:

```
## Security Analysis Results

### Critical Issues
- [CRITICAL] Description
  - File: path/to/file.py:line
  - Risk: What could happen
  - Fix: How to fix it

### Warnings
- [WARNING] Description...

### Notes
- [INFO] Description...
```

## Examples

### Example 1: SQL Injection

Input:
```python
query = f"SELECT * FROM users WHERE id = {user_id}"
```

Finding:
- [CRITICAL] SQL Injection vulnerability
  - Risk: Attackers can execute arbitrary SQL
  - Fix: Use parameterized queries
```

### skill.yaml Format

The skill.yaml file contains metadata:

```yaml
# Required fields
name: security-scan
version: 1.2.3
description: Identifies security vulnerabilities in code

# Discovery metadata (for smart index)
keywords:
  - security
  - vulnerability
  - sql injection
  - xss
  - owasp

# Optional authorship info
author: security-team
license: MIT
repository: https://github.com/org/security-scan-skill

# Permission declarations
permissions:
  tools:
    - bash        # Can execute shell commands
    - file_read   # Can read files
    - file_write  # Can write files (use sparingly!)
  network: false  # Needs network access?
  filesystem:
    read:
      - "*.py"
      - "*.js"
      - "*.java"
      - "src/**/*"
    write: []     # No write access

# Dependencies (optional)
dependencies:
  skills:
    - code-analysis  # Requires another skill
  packages: []       # Python packages (future)

# Compatibility
compatible_with:
  - inkarms
  - claude
  - codex
```

## Permission System

Skills declare what they need. InkArms enforces these at runtime.

### Available Permissions

| Permission | Description |
|------------|-------------|
| `bash` | Execute shell commands |
| `file_read` | Read files |
| `file_write` | Write/create files |
| `web_search` | Search the web (plugin) |
| `web_fetch` | Fetch URLs |

### Filesystem Permissions

Use glob patterns to restrict file access:

```yaml
permissions:
  filesystem:
    read:
      - "*.py"           # Python files in current dir
      - "src/**/*.js"    # JS files under src/
      - "!**/test_*"     # Exclude test files
    write:
      - "output/*.md"    # Only write to output/
```

### Network Permissions

```yaml
permissions:
  network: true   # Skill may make network requests
```

## Writing Effective Instructions

### Be Specific

❌ Bad:
```markdown
## Instructions
Review the code and find issues.
```

✅ Good:
```markdown
## Instructions

When reviewing code:

1. **First Pass: Structure**
   - Check file organization
   - Verify naming conventions
   - Look for code duplication

2. **Second Pass: Logic**
   - Trace data flow
   - Identify edge cases
   - Check error handling

3. **Third Pass: Style**
   - Verify consistent formatting
   - Check documentation
   - Review comments
```

### Provide Context

```markdown
## Background

This skill is designed for Python web applications
using Django or Flask. It assumes:

- Python 3.8+
- Standard project structure
- Virtual environment usage
```

### Include Examples

```markdown
## Examples

### Example 1: Good Code

```python
def calculate_total(items: list[Item]) -> Decimal:
    """Calculate total price with tax."""
    subtotal = sum(item.price for item in items)
    return subtotal * Decimal("1.08")
```

This is good because:
- Type hints are present
- Docstring explains purpose
- Uses Decimal for money

### Example 2: Code Needing Improvement

```python
def calc(x):
    return sum([i['p'] for i in x]) * 1.08
```

Issues:
- Unclear naming
- No type hints
- Float for money (precision issues)
```

### Define Output Format

```markdown
## Output Format

Always return results as a markdown document with these sections:

1. **Summary** (2-3 sentences)
2. **Findings** (bulleted list with severity)
3. **Recommendations** (numbered, actionable)
4. **Code Examples** (if applicable)

Example output:

```markdown
## Summary
The code has 3 critical issues and 5 warnings...

## Findings
- [CRITICAL] SQL injection in user_query()
- [WARNING] Missing input validation...

## Recommendations
1. Use parameterized queries
2. Add input validation...
```
```

## Skill Discovery: Keywords

InkArms uses keywords to find relevant skills. Choose wisely:

```yaml
keywords:
  # Primary concepts
  - security
  - vulnerability
  - audit

  # Specific techniques
  - sql injection
  - xss
  - csrf

  # Related technologies
  - owasp
  - penetration testing

  # Common user phrases
  - security scan
  - find vulnerabilities
  - security review
```

Tips:
- Include synonyms
- Add common misspellings (if relevant)
- Think about what users might type
- Include both technical and plain language terms

## Testing Your Skill

### Manual Testing

```bash
# Validate the skill
inkarms skill validate ./my-skill

# Load it explicitly
inkarms run "Test query" --skill my-skill

# Check if it's indexed
inkarms skill show my-skill
```

### Integration Testing

Create test cases:

```bash
# tests/skills/test_my_skill/
├── input.txt        # Test input
├── expected.txt     # Expected behavior description
└── run_test.sh      # Test script
```

## Distributing Skills

### Via Git Repository

The recommended way:

```bash
# Create a repo for your skill
git init my-awesome-skill
cd my-awesome-skill
# ... add SKILL.md and skill.yaml ...
git add .
git commit -m "Initial skill"
git remote add origin https://github.com/you/my-awesome-skill
git push -u origin main
```

Users install with:

```bash
inkarms skill install github:you/my-awesome-skill
```

### Via Skill Collection Repository

Group related skills together:

```
my-skill-collection/
├── README.md
├── security-scan/
│   ├── SKILL.md
│   └── skill.yaml
├── code-review/
│   ├── SKILL.md
│   └── skill.yaml
└── documentation/
    ├── SKILL.md
    └── skill.yaml
```

Users install individual skills:

```bash
inkarms skill install github:you/my-skill-collection/security-scan
```

## Best Practices

### 1. Single Responsibility

Each skill should do one thing well:

❌ `general-helper` — Does everything
✅ `security-scan` — Finds security issues
✅ `api-design` — Helps design APIs
✅ `test-generator` — Creates tests

### 2. Minimal Permissions

Request only what you need:

```yaml
# Only reads Python files, no write access, no network
permissions:
  tools:
    - file_read
  network: false
  filesystem:
    read:
      - "*.py"
    write: []
```

### 3. Version Your Skills

Use semantic versioning:

```yaml
version: 1.2.3
# 1 = Major (breaking changes)
# 2 = Minor (new features)
# 3 = Patch (bug fixes)
```

### 4. Document Everything

- What the skill does
- When to use it
- What output to expect
- Examples of good and bad cases

### 5. Test Before Publishing

```bash
inkarms skill validate ./my-skill
inkarms run "test query" --skill ./my-skill
```

---

## Skill Templates

### Code Review Skill

```markdown
---
name: code-review
description: Comprehensive code review assistant
---

# Code Review Skill

## Instructions

Perform a thorough code review focusing on:

1. **Correctness** - Does it work as intended?
2. **Readability** - Is it easy to understand?
3. **Maintainability** - Will it be easy to modify?
4. **Performance** - Are there obvious inefficiencies?
5. **Security** - Are there vulnerabilities?

## Output Format

## Code Review

### Summary
[2-3 sentence overview]

### Issues Found

#### Critical
- [ ] Issue description (file:line)

#### Suggestions
- [ ] Suggestion (file:line)

### Positive Notes
- Good use of...

### Recommended Actions
1. First priority...
2. Second priority...
```

### Documentation Generator

```markdown
---
name: doc-generator
description: Generates documentation from code
---

# Documentation Generator

## Instructions

Generate comprehensive documentation including:

1. **Overview** - What does this code do?
2. **Installation** - How to set it up
3. **Usage** - How to use it
4. **API Reference** - Function/class documentation
5. **Examples** - Working code examples

## Output Format

# [Project Name]

## Overview
[Description]

## Installation
```bash
[commands]
```

## Usage
[Examples]

## API Reference
### function_name(args)
[Description]
```

---

*"A well-crafted skill is a gift that keeps on giving."* 🐙
