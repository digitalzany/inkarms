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
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            # Log query via log_query
            logger.log_query("What is AI?", platform="cli", model="gpt-4")

            # Read log file
            with log_path.open() as f:
                lines = f.readlines()

            assert len(lines) == 1

            event = json.loads(lines[0])
            assert event["content"] == "What is AI?"
            assert event["model"] == "gpt-4"
            assert event["event_type"] == AuditEventType.QUERY_COMPLETE.value

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
            logger.log_query("Sensitive query", platform="cli")

            # Read log
            with log_path.open() as f:
                event = json.loads(f.readline())

            # Content should be hashed
            assert event["content"] != "Sensitive query"
            assert len(event["content"]) == 64  # SHA256 hash length

    def test_include_responses_false(self) -> None:
        """Test that stdout/stderr are not logged when include_responses is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path, buffer_size=1, include_responses=False
            )

            logger.log_command_complete("ls", exit_code=0, stdout="file1", stderr="")

            with log_path.open() as f:
                event = json.loads(f.readline())

            assert "stdout" not in event
            assert "stderr" not in event

    def test_include_queries_false(self) -> None:
        """Test that content is hashed when include_queries is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(
                log_path=log_path,
                buffer_size=1,
                include_queries=False,
                hash_queries=True,
            )

            # Log query
            logger.log_query("Secret query", platform="cli")

            # Read log
            with log_path.open() as f:
                event = json.loads(f.readline())

            # Content should be hashed (hash_queries takes precedence)
            assert len(event["content"]) == 64

    def test_tool_events(self) -> None:
        """Test logging tool execution events."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_tool_start("bash", "call-1", parameters={"command": "ls"})
            logger.log_tool_complete("bash", "call-1", execution_time=0.1, output_preview="file1")
            logger.log_tool_denied("bash", "call-2", reason="dangerous")
            logger.log_tool_error("bash", "call-3", execution_time=0.05, error="timeout")

            with log_path.open() as f:
                lines = f.readlines()

            events = [json.loads(line) for line in lines]
            assert events[0]["event_type"] == AuditEventType.TOOL_START.value
            assert events[0]["tool_name"] == "bash"
            assert events[1]["event_type"] == AuditEventType.TOOL_COMPLETE.value
            assert events[2]["event_type"] == AuditEventType.TOOL_DENIED.value
            assert events[3]["event_type"] == AuditEventType.TOOL_ERROR.value

    def test_hub_cron_run(self) -> None:
        """Test logging cron job execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_hub_cron_run(job_id="job-1", result="OK: done")

            with log_path.open() as f:
                event = json.loads(f.readline())

            assert event["event_type"] == AuditEventType.HUB_CRON_RUN.value
            assert event["job_id"] == "job-1"
            assert event["result"] == "OK: done"

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

    def test_hub_trigger_fired(self) -> None:
        """Test logging hub trigger invocations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path=log_path, buffer_size=1)

            logger.log_hub_trigger_fired("my-trigger", "session-1", status_code=200)

            with log_path.open() as f:
                event = json.loads(f.readline())

            assert event["event_type"] == AuditEventType.HUB_TRIGGER_FIRED.value
            assert event["trigger_name"] == "my-trigger"
            assert event["status_code"] == 200
