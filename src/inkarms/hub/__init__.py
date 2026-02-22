"""
InkArms Hub — always-on daemon.

The hub runs platform adapters as persistent background tasks, exposes a
REST + WebSocket API for CLI ↔ daemon communication, manages scheduled AI
queries (cron via APScheduler), accepts webhook triggers for AI actions, and
optionally proxies OpenAI-compatible completions requests.

Install as a system service: ``inkarms hub install``
Start in background:         ``inkarms hub start --background``
"""
