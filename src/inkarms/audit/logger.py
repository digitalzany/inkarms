"""
Audit logging for InkArms operations.

This module provides JSON Lines based audit logging for tracking
commands, queries, and system events.
"""

import atexit
import gzip
import hashlib
import json
import re
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(str, Enum):
    """Types of audit events."""

    # Command execution
    COMMAND_START = "command_start"
    COMMAND_COMPLETE = "command_complete"
    COMMAND_BLOCKED = "command_blocked"
    COMMAND_ERROR = "command_error"

    # Query operations
    QUERY_COMPLETE = "query_complete"

    # Tool execution events
    TOOL_START = "tool_start"
    TOOL_COMPLETE = "tool_complete"
    TOOL_DENIED = "tool_denied"
    TOOL_ERROR = "tool_error"

    # Platform messaging events
    PLATFORM_MESSAGE_RECEIVED = "platform_message_received"
    PLATFORM_MESSAGE_SENT = "platform_message_sent"
    PLATFORM_ADAPTER_STARTED = "platform_adapter_started"
    PLATFORM_ADAPTER_STOPPED = "platform_adapter_stopped"
    PLATFORM_ADAPTER_ERROR = "platform_adapter_error"

    # Hub daemon events
    HUB_STARTED = "hub_started"
    HUB_STOPPED = "hub_stopped"
    HUB_CRON_RUN = "hub_cron_run"
    HUB_TRIGGER_FIRED = "hub_trigger_fired"


class AuditLogger:
    """
    JSON Lines based audit logger.

    Logs events to a JSON Lines file with rotation and compression support.
    """

    def __init__(
        self,
        log_path: str | Path,
        enable: bool = True,
        rotation: str = "daily",
        max_size_mb: int = 100,
        retention_days: int = 90,
        compress_old: bool = True,
        include_responses: bool = False,
        include_queries: bool = True,
        hash_queries: bool = False,
        redact_paths: bool = True,
        redact_patterns: list[str] | None = None,
        buffer_size: int = 100,
        flush_interval_seconds: int = 5,
    ) -> None:
        """
        Initialize audit logger.

        Args:
            log_path: Path to audit log file
            enable: Whether logging is enabled
            rotation: Rotation strategy (daily, weekly, size)
            max_size_mb: Maximum log file size in MB before rotation
            retention_days: Days to keep old logs
            compress_old: Whether to compress rotated logs
            include_responses: Whether to log full responses
            include_queries: Whether to log full queries
            hash_queries: Whether to hash queries for privacy
            redact_paths: Whether to redact file paths
            redact_patterns: Additional patterns to redact
            buffer_size: Number of events to buffer before flush
            flush_interval_seconds: Seconds between forced flushes
        """
        self.log_path = Path(log_path).expanduser()
        self.enable = enable
        self.rotation = rotation
        self.max_size_mb = max_size_mb
        self.retention_days = retention_days
        self.compress_old = compress_old
        self.include_responses = include_responses
        self.include_queries = include_queries
        self.hash_queries = hash_queries
        self.redact_paths = redact_paths
        self.redact_patterns = redact_patterns or []
        self.buffer_size = buffer_size
        self.flush_interval_seconds = flush_interval_seconds

        # Internal state
        self._buffer: list[dict[str, Any]] = []
        self._last_flush = datetime.now()

        # Ensure log directory exists
        if self.enable:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            atexit.register(self.flush)

    @classmethod
    def from_config(cls, config: Any) -> "AuditLogger":
        """
        Create audit logger from configuration.

        Args:
            config: AuditLogConfig instance

        Returns:
            Configured AuditLogger
        """
        return cls(
            log_path=config.path,
            enable=config.enable,
            rotation=config.rotation,
            max_size_mb=config.max_size_mb,
            retention_days=config.retention_days,
            compress_old=config.compress_old,
            include_responses=config.include_responses,
            include_queries=config.include_queries,
            hash_queries=config.hash_queries,
            redact_paths=config.redact_paths,
            redact_patterns=config.redact_patterns,
            buffer_size=config.buffer_size,
            flush_interval_seconds=config.flush_interval_seconds,
        )

    def _redact_text(self, text: str) -> str:
        """
        Redact sensitive information from text.

        Args:
            text: Text to redact

        Returns:
            Redacted text
        """
        redacted = text

        # Redact file paths if enabled
        if self.redact_paths:
            # Redact absolute paths
            redacted = re.sub(r"/[a-zA-Z0-9/_.-]+", "[PATH]", redacted)
            # Redact home directory references
            redacted = re.sub(r"~[a-zA-Z0-9/_.-]*", "[HOME]", redacted)

        # Apply custom redaction patterns
        for pattern in self.redact_patterns:
            redacted = re.sub(pattern, "[REDACTED]", redacted)

        return redacted

    @staticmethod
    def _hash_text(text: str) -> str:
        """
        Hash text for privacy-preserving logging.

        Args:
            text: Text to hash

        Returns:
            SHA256 hash of text
        """
        return hashlib.sha256(text.encode()).hexdigest()

    @staticmethod
    def _create_event(event_type: AuditEventType, data: dict[str, Any]) -> dict[str, Any]:
        """
        Create an audit event.

        Args:
            event_type: Type of event
            data: Event-specific data

        Returns:
            Complete event dictionary
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type.value,
            **data,
        }
        return event

    def _write_event(self, event: dict[str, Any]) -> None:
        """
        Write an event to the log.

        Args:
            event: Event dictionary
        """
        if not self.enable:
            return

        # Add to buffer
        self._buffer.append(event)

        # Flush if buffer is full or interval elapsed
        now = datetime.now()
        should_flush = (
            len(self._buffer) >= self.buffer_size
            or (now - self._last_flush).seconds >= self.flush_interval_seconds
        )

        if should_flush:
            self.flush()

    def flush(self) -> None:
        """Flush buffered events to disk."""
        if not self.enable or not self._buffer:
            return

        # Check for rotation
        self._rotate_if_needed()

        # Write buffered events
        with self.log_path.open("a") as f:
            for event in self._buffer:
                f.write(json.dumps(event) + "\n")

        # Clear buffer
        self._buffer.clear()
        self._last_flush = datetime.now()

    def _rotate_if_needed(self) -> None:
        """Rotate log file if needed based on configuration."""
        if not self.log_path.exists():
            return

        should_rotate = False

        # Check size-based rotation
        if self.rotation == "size":
            size_mb = self.log_path.stat().st_size / (1024 * 1024)
            if size_mb >= self.max_size_mb:
                should_rotate = True

        # Check time-based rotation
        elif self.rotation == "daily":
            mtime = datetime.fromtimestamp(self.log_path.stat().st_mtime)
            if mtime.date() < datetime.now().date():
                should_rotate = True

        elif self.rotation == "weekly":
            mtime = datetime.fromtimestamp(self.log_path.stat().st_mtime)
            if (datetime.now() - mtime).days >= 7:
                should_rotate = True

        if should_rotate:
            self._rotate_log()

    def _rotate_log(self) -> None:
        """Rotate the current log file."""
        # Generate rotated filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        rotated_name = f"{self.log_path.stem}_{timestamp}{self.log_path.suffix}"
        rotated_path = self.log_path.parent / rotated_name

        # Rename current log
        self.log_path.rename(rotated_path)

        # Compress if enabled
        if self.compress_old:
            self._compress_log(rotated_path)

        # Clean old logs
        self._clean_old_logs()

    @staticmethod
    def _compress_log(log_path: Path) -> None:
        """Compress a log file with gzip."""
        compressed_path = log_path.with_suffix(log_path.suffix + ".gz")

        with log_path.open("rb") as f_in, gzip.open(compressed_path, "wb") as f_out:
            f_out.write(f_in.read())

        # Remove uncompressed file
        log_path.unlink()

    def _clean_old_logs(self) -> None:
        """Remove logs older than retention period."""
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        # Find old log files
        pattern = f"{self.log_path.stem}_*{self.log_path.suffix}*"
        for old_log in self.log_path.parent.glob(pattern):
            mtime = datetime.fromtimestamp(old_log.stat().st_mtime)
            if mtime < cutoff:
                old_log.unlink()

    # Convenience methods for logging specific events

    def log_command_start(self, command: str) -> None:
        """Log the start of a command execution."""
        event = self._create_event(
            AuditEventType.COMMAND_START,
            {"command": command if not self.hash_queries else self._hash_text(command)},
        )
        self._write_event(event)

    def log_command_complete(
        self, command: str, exit_code: int, stdout: str = "", stderr: str = ""
    ) -> None:
        """Log a completed command execution."""
        data: dict[str, Any] = {
            "command": command if not self.hash_queries else self._hash_text(command),
            "exit_code": exit_code,
        }

        if self.include_responses:
            data["stdout"] = stdout
            data["stderr"] = stderr

        event = self._create_event(AuditEventType.COMMAND_COMPLETE, data)
        self._write_event(event)

    def log_command_blocked(self, command: str, reason: str) -> None:
        """Log a blocked command."""
        event = self._create_event(
            AuditEventType.COMMAND_BLOCKED,
            {
                "command": command if not self.hash_queries else self._hash_text(command),
                "reason": reason,
            },
        )
        self._write_event(event)

    def log_command_error(self, command: str, error: str) -> None:
        """Log a command execution error."""
        event = self._create_event(
            AuditEventType.COMMAND_ERROR,
            {
                "command": command if not self.hash_queries else self._hash_text(command),
                "error": error,
            },
        )
        self._write_event(event)

    def log_query(
        self,
        content: str,
        platform: str = "cli",
        session_id: str | None = None,
        metadata: dict | None = None,
        model: str | None = None,
    ) -> None:
        """Log a generic query or response.

        This is a simplified logging method for general query/response logging.
        """
        data = {
            "content": content if self.include_queries and not self.hash_queries else self._hash_text(content),
            "platform": platform,
        }
        if session_id:
            data["session_id"] = session_id
        if metadata:
            data["metadata"] = metadata
        if model:
            data["model"] = model

        event = self._create_event(AuditEventType.QUERY_COMPLETE, data)
        self._write_event(event)

    def log_platform_message_received(
        self,
        platform: str,
        user_id: str,
        username: str | None,
        message: str,
        session_id: str | None = None,
    ) -> None:
        """Log a message received from a platform."""
        data: dict[str, Any] = {
            "platform": platform,
            "user_id": user_id,
            "session_id": session_id,
        }

        if username:
            data["username"] = username

        if self.include_queries:
            # We explicitly cast to str or handle potential non-str types if needed,
            # though the signature says 'message' is str.
            msg_content = message if not self.hash_queries else self._hash_text(message)
            # data is dict[str, Any], so this assignment is valid in Python but mypy might be confused
            # by previous usage or inference. We force it.
            data.update({"message": str(msg_content)})
        else:
            data.update({"message_hash": self._hash_text(message)})

        event = self._create_event(AuditEventType.PLATFORM_MESSAGE_RECEIVED, data)
        self._write_event(event)

    def log_platform_message_sent(
        self,
        platform: str,
        user_id: str,
        response: str,
        session_id: str | None = None,
        tokens: int = 0,
        cost: float = 0.0,
        model: str | None = None,
    ) -> None:
        """Log a message sent to a platform."""
        data: dict[str, Any] = {
            "platform": platform,
            "user_id": user_id,
            "session_id": session_id,
            "tokens": tokens,
            "cost": cost,
        }

        if model:
            data["model"] = model

        if self.include_responses:
            data["response"] = response
        else:
            data["response_hash"] = self._hash_text(response)

        event = self._create_event(AuditEventType.PLATFORM_MESSAGE_SENT, data)
        self._write_event(event)

    def log_platform_adapter_started(self, platform: str, mode: str) -> None:
        """Log a platform adapter start."""
        event = self._create_event(
            AuditEventType.PLATFORM_ADAPTER_STARTED,
            {
                "platform": platform,
                "mode": mode,
            },
        )
        self._write_event(event)

    def log_platform_adapter_stopped(self, platform: str) -> None:
        """Log a platform adapter stop."""
        event = self._create_event(
            AuditEventType.PLATFORM_ADAPTER_STOPPED,
            {"platform": platform},
        )
        self._write_event(event)

    def log_platform_adapter_error(self, platform: str, error: str) -> None:
        """Log a platform adapter error."""
        event = self._create_event(
            AuditEventType.PLATFORM_ADAPTER_ERROR,
            {
                "platform": platform,
                "error": error,
            },
        )
        self._write_event(event)

    # Hub daemon events

    def log_hub_started(self, host: str, port: int) -> None:
        """Log hub daemon start."""
        event = self._create_event(
            AuditEventType.HUB_STARTED,
            {"host": host, "port": port},
        )
        self._write_event(event)

    def log_hub_stopped(self, uptime_seconds: float) -> None:
        """Log hub daemon stop."""
        event = self._create_event(
            AuditEventType.HUB_STOPPED,
            {"uptime_seconds": uptime_seconds},
        )
        self._write_event(event)

    def log_hub_cron_run(self, job_id: str, result: str = "") -> None:
        """Log a cron job execution."""
        event = self._create_event(
            AuditEventType.HUB_CRON_RUN,
            {"job_id": job_id, "result": result},
        )
        self._write_event(event)

    def log_hub_trigger_fired(
        self,
        trigger_name: str,
        session_id: str,
        status_code: int,
    ) -> None:
        """Log a webhook trigger invocation."""
        event = self._create_event(
            AuditEventType.HUB_TRIGGER_FIRED,
            {
                "trigger_name": trigger_name,
                "session_id": session_id,
                "status_code": status_code,
            },
        )
        self._write_event(event)

    # Tool execution events

    def log_tool_start(
        self,
        tool_name: str,
        tool_call_id: str,
        parameters: dict[str, Any] | None = None,
        is_dangerous: bool = False,
    ) -> None:
        """Log the start of a tool execution."""
        data: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "is_dangerous": is_dangerous,
        }
        if parameters is not None:
            data["parameters"] = self._redact_parameters(parameters)
        event = self._create_event(AuditEventType.TOOL_START, data)
        self._write_event(event)

    def log_tool_complete(
        self,
        tool_name: str,
        tool_call_id: str,
        execution_time: float,
        output_preview: str = "",
        exit_code: int | None = None,
    ) -> None:
        """Log a completed tool execution."""
        data: dict[str, Any] = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "execution_time": execution_time,
        }
        if output_preview:
            data["output_preview"] = output_preview[:200]
        if exit_code is not None:
            data["exit_code"] = exit_code
        event = self._create_event(AuditEventType.TOOL_COMPLETE, data)
        self._write_event(event)

    def log_tool_error(
        self,
        tool_name: str,
        tool_call_id: str,
        execution_time: float,
        error: str,
    ) -> None:
        """Log a tool execution error."""
        event = self._create_event(
            AuditEventType.TOOL_ERROR,
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "execution_time": execution_time,
                "error": error,
            },
        )
        self._write_event(event)

    def log_tool_denied(
        self,
        tool_name: str,
        tool_call_id: str,
        reason: str,
    ) -> None:
        """Log a denied tool execution."""
        event = self._create_event(
            AuditEventType.TOOL_DENIED,
            {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "reason": reason,
            },
        )
        self._write_event(event)

    def _redact_parameters(self, parameters: dict[str, Any]) -> dict[str, Any]:
        """Redact sensitive values in tool parameters.

        Args:
            parameters: Raw parameter dict.

        Returns:
            Redacted parameter dict.
        """
        redacted = {}
        for key, value in parameters.items():
            if isinstance(value, str):
                if self.hash_queries:
                    redacted[key] = self._hash_text(value)
                elif self.redact_paths:
                    redacted[key] = self._redact_text(value)
                else:
                    redacted[key] = value
            else:
                redacted[key] = value
        return redacted


# Singleton instance
_audit_logger: AuditLogger | None = None


def get_audit_logger(config: Any | None = None) -> AuditLogger:
    """
    Get or create the global audit logger instance.

    Args:
        config: Optional AuditLogConfig for initialization

    Returns:
        AuditLogger instance
    """
    global _audit_logger

    if _audit_logger is None:
        if config is None:
            # Import here to avoid circular dependency
            from inkarms.config.loader import get_config

            config = get_config().security.audit_log

        _audit_logger = AuditLogger.from_config(config)

    return _audit_logger
