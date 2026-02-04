"""Tests for audit logger."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

from inkarms.audit.logger import AuditEventType, AuditLogger


class TestAuditLogger:
    """Test AuditLogger functionality."""

    def test_create_audit_logger(self) -> None:
        """Test creating an audit logger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path)

            assert logger.log_path == log_path
            assert logger.enable is True

    def test_log_command_events(self) -> None:
        """Test logging command events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path, buffer_size=1  # Flush immediately
            )

            # Log command events
            logger.log_command_start("ls -la")
            logger.log_command_complete("ls -la", exit_code=0, stdout="file1\nfile2")
            logger.log_command_blocked("rm -rf /", "Not in whitelist")
            logger.log_command_error("invalid", "Command not found")

            # Read log file
            with log_path.open() as f:
                lines = f.readlines()

            assert len(lines) == 4

            # Check event types
            events = [json.loads(line) for line in lines]
            assert events[0]["event_type"] == AuditEventType.COMMAND_START.value
            assert events[1]["event_type"] == AuditEventType.COMMAND_COMPLETE.value
            assert events[2]["event_type"] == AuditEventType.COMMAND_BLOCKED.value
            assert events[3]["event_type"] == AuditEventType.COMMAND_ERROR.value

    def test_log_query_events(self) -> None:
        """Test logging query events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path, buffer_size=1, include_responses=True
            )

            # Log query events
            logger.log_query_start("What is AI?", "gpt-4")
            logger.log_query_complete(
                "What is AI?",
                "gpt-4",
                response="AI is artificial intelligence",
                tokens=100,
                cost=0.01,
            )
            logger.log_query_error("Bad query", "gpt-4", "Rate limit exceeded")

            # Read log file
            with log_path.open() as f:
                lines = f.readlines()

            assert len(lines) == 3

            # Check event content
            events = [json.loads(line) for line in lines]
            assert events[0]["query"] == "What is AI?"
            assert events[0]["model"] == "gpt-4"
            assert events[1]["tokens"] == 100
            assert events[1]["cost"] == 0.01
            assert "response" in events[1]  # Because include_responses=True

    def test_buffering(self) -> None:
        """Test event buffering."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=5)

            # Log 3 events (should not flush yet)
            logger.log_command_start("cmd1")
            logger.log_command_start("cmd2")
            logger.log_command_start("cmd3")

            # File should not exist yet
            assert not log_path.exists()

            # Log 2 more events (should trigger flush)
            logger.log_command_start("cmd4")
            logger.log_command_start("cmd5")

            # Now file should exist with 5 events
            with log_path.open() as f:
                lines = f.readlines()
            assert len(lines) == 5

    def test_manual_flush(self) -> None:
        """Test manual flush."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=100)

            # Log an event
            logger.log_command_start("test")

            # File should not exist yet
            assert not log_path.exists()

            # Manual flush
            logger.flush()

            # Now file should exist
            assert log_path.exists()
            with log_path.open() as f:
                lines = f.readlines()
            assert len(lines) == 1

    def test_disabled_logger(self) -> None:
        """Test that disabled logger doesn't write anything."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, enable=False)

            # Log events
            logger.log_command_start("test")
            logger.flush()

            # File should not be created
            assert not log_path.exists()

    def test_query_hashing(self) -> None:
        """Test query hashing for privacy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path, buffer_size=1, hash_queries=True
            )

            # Log query
            logger.log_query_start("Sensitive query", "gpt-4")

            # Read log
            with log_path.open() as f:
                event = json.loads(f.readline())

            # Query should be hashed
            assert event["query"] != "Sensitive query"
            assert len(event["query"]) == 64  # SHA256 hash length

    def test_include_responses_false(self) -> None:
        """Test that responses are not logged when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path, buffer_size=1, include_responses=False
            )

            # Log query with response
            logger.log_query_complete(
                "query", "gpt-4", response="This should not be logged"
            )

            # Read log
            with log_path.open() as f:
                event = json.loads(f.readline())

            # Response should not be present
            assert "response" not in event

    def test_include_queries_false(self) -> None:
        """Test that queries are not logged when disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path,
                buffer_size=1,
                include_queries=False,
                hash_queries=True,
            )

            # Log query
            logger.log_query_start("Secret query", "gpt-4")

            # Read log
            with log_path.open() as f:
                event = json.loads(f.readline())

            # Query should be hashed (hash_queries takes precedence)
            assert len(event["query"]) == 64

    def test_skill_events(self) -> None:
        """Test logging skill events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_skill_installed("test-skill", "github:user/repo")
            logger.log_skill_removed("test-skill")

            with log_path.open() as f:
                lines = f.readlines()

            events = [json.loads(line) for line in lines]
            assert events[0]["event_type"] == AuditEventType.SKILL_INSTALLED.value
            assert events[0]["skill_name"] == "test-skill"
            assert events[1]["event_type"] == AuditEventType.SKILL_REMOVED.value

    def test_session_events(self) -> None:
        """Test logging session events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_session_start("session-123")
            logger.log_session_end("session-123", total_tokens=500, total_cost=0.05)

            with log_path.open() as f:
                lines = f.readlines()

            events = [json.loads(line) for line in lines]
            assert events[0]["event_type"] == AuditEventType.SESSION_START.value
            assert events[0]["session_id"] == "session-123"
            assert events[1]["total_tokens"] == 500
            assert events[1]["total_cost"] == 0.05

    def test_close_flushes_buffer(self) -> None:
        """Test that close() flushes remaining events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=100)

            # Log an event
            logger.log_command_start("test")

            # Close logger
            logger.close()

            # Event should be flushed
            assert log_path.exists()
            with log_path.open() as f:
                lines = f.readlines()
            assert len(lines) == 1

    def test_timestamp_format(self) -> None:
        """Test that timestamps are in ISO format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_command_start("test")

            with log_path.open() as f:
                event = json.loads(f.readline())

            # Check timestamp exists and is ISO formatted
            assert "timestamp" in event
            # Should parse without error
            datetime.fromisoformat(event["timestamp"])

    def test_config_change_event(self) -> None:
        """Test logging configuration changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_config_changed("providers.default", "gpt-4", "claude-3")

            with log_path.open() as f:
                event = json.loads(f.readline())

            assert event["event_type"] == AuditEventType.CONFIG_CHANGED.value
            assert event["key"] == "providers.default"
            assert event["old_value"] == "gpt-4"
            assert event["new_value"] == "claude-3"
