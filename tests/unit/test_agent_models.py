"""Tests for agent models."""

import pytest

from inkarms.agent.models import AgentConfig, ApprovalMode


class TestApprovalMode:
    """Tests for ApprovalMode enum."""

    def test_approval_modes(self):
        """Test approval mode values."""
        assert ApprovalMode.AUTO == "auto"
        assert ApprovalMode.MANUAL == "manual"
        assert ApprovalMode.DISABLED == "disabled"


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = AgentConfig()

        assert config.approval_mode == ApprovalMode.MANUAL
        assert config.max_iterations == 10
        assert config.enable_tools is True
        assert config.allowed_tools is None
        assert config.blocked_tools is None
        assert config.timeout_per_iteration == 300

    def test_custom_config(self):
        """Test custom configuration."""
        config = AgentConfig(
            approval_mode=ApprovalMode.AUTO,
            max_iterations=20,
            enable_tools=True,
            allowed_tools=["execute_bash", "read_file"],
            blocked_tools=["write_file"],
            timeout_per_iteration=600,
        )

        assert config.approval_mode == ApprovalMode.AUTO
        assert config.max_iterations == 20
        assert config.allowed_tools == ["execute_bash", "read_file"]
        assert config.blocked_tools == ["write_file"]
        assert config.timeout_per_iteration == 600

    def test_max_iterations_validation(self):
        """Test max_iterations validation."""
        # Valid values
        AgentConfig(max_iterations=1)
        AgentConfig(max_iterations=50)

        # Invalid values
        with pytest.raises(Exception):  # Pydantic validation error
            AgentConfig(max_iterations=0)

        with pytest.raises(Exception):
            AgentConfig(max_iterations=51)

    def test_timeout_validation(self):
        """Test timeout_per_iteration validation."""
        # Valid values
        AgentConfig(timeout_per_iteration=10)
        AgentConfig(timeout_per_iteration=600)

        # Invalid values
        with pytest.raises(Exception):  # Pydantic validation error
            AgentConfig(timeout_per_iteration=9)

        with pytest.raises(Exception):
            AgentConfig(timeout_per_iteration=601)

    def test_is_tool_allowed_tools_disabled(self):
        """Test tool allowed check when tools are disabled."""
        config = AgentConfig(enable_tools=False)

        allowed, reason = config.is_tool_allowed("execute_bash", is_dangerous=True)

        assert allowed is False
        assert "disabled" in reason.lower()

    def test_is_tool_allowed_approval_disabled(self):
        """Test tool allowed check when approval mode is disabled."""
        config = AgentConfig(approval_mode=ApprovalMode.DISABLED)

        allowed, reason = config.is_tool_allowed("read_file", is_dangerous=False)

        assert allowed is False
        assert "disabled" in reason.lower()

    def test_is_tool_allowed_blocked_tool(self):
        """Test tool allowed check for blocked tool."""
        config = AgentConfig(blocked_tools=["write_file", "execute_bash"])

        allowed, reason = config.is_tool_allowed("write_file", is_dangerous=True)

        assert allowed is False
        assert "blocked" in reason.lower()

    def test_is_tool_allowed_not_in_whitelist(self):
        """Test tool allowed check for tool not in whitelist."""
        config = AgentConfig(allowed_tools=["read_file", "list_files"])

        allowed, reason = config.is_tool_allowed("execute_bash", is_dangerous=True)

        assert allowed is False
        assert "not in allowed list" in reason.lower()

    def test_is_tool_allowed_dangerous_manual_mode(self):
        """Test tool allowed check for dangerous tool in manual mode."""
        config = AgentConfig(approval_mode=ApprovalMode.MANUAL)

        allowed, reason = config.is_tool_allowed("execute_bash", is_dangerous=True)

        assert allowed is False
        assert "requires manual approval" in reason.lower()

    def test_is_tool_allowed_dangerous_auto_mode(self):
        """Test tool allowed check for dangerous tool in auto mode."""
        config = AgentConfig(approval_mode=ApprovalMode.AUTO)

        allowed, reason = config.is_tool_allowed("execute_bash", is_dangerous=True)

        assert allowed is True
        assert reason == ""

    def test_is_tool_allowed_safe_tool_manual_mode(self):
        """Test tool allowed check for safe tool in manual mode."""
        config = AgentConfig(approval_mode=ApprovalMode.MANUAL)

        allowed, reason = config.is_tool_allowed("read_file", is_dangerous=False)

        assert allowed is True
        assert reason == ""

    def test_is_tool_allowed_safe_tool_auto_mode(self):
        """Test tool allowed check for safe tool in auto mode."""
        config = AgentConfig(approval_mode=ApprovalMode.AUTO)

        allowed, reason = config.is_tool_allowed("read_file", is_dangerous=False)

        assert allowed is True
        assert reason == ""

    def test_is_tool_allowed_priority_order(self):
        """Test that blocklist takes priority over whitelist."""
        config = AgentConfig(
            allowed_tools=["execute_bash", "read_file"],
            blocked_tools=["execute_bash"],
        )

        # Blocked takes priority
        allowed, reason = config.is_tool_allowed("execute_bash", is_dangerous=True)
        assert allowed is False
        assert "blocked" in reason.lower()

        # Not blocked but in whitelist
        allowed, reason = config.is_tool_allowed("read_file", is_dangerous=False)
        assert allowed is True

    def test_is_tool_allowed_with_whitelist_only(self):
        """Test tool filtering with whitelist only."""
        config = AgentConfig(
            approval_mode=ApprovalMode.AUTO,
            allowed_tools=["read_file", "list_files"],
        )

        # In whitelist
        allowed, _ = config.is_tool_allowed("read_file", is_dangerous=False)
        assert allowed is True

        # Not in whitelist
        allowed, _ = config.is_tool_allowed("write_file", is_dangerous=True)
        assert allowed is False

    def test_is_tool_allowed_with_blocklist_only(self):
        """Test tool filtering with blocklist only."""
        config = AgentConfig(
            approval_mode=ApprovalMode.AUTO,
            blocked_tools=["execute_bash"],
        )

        # Not blocked
        allowed, _ = config.is_tool_allowed("read_file", is_dangerous=False)
        assert allowed is True

        # Blocked
        allowed, _ = config.is_tool_allowed("execute_bash", is_dangerous=True)
        assert allowed is False

    def test_is_tool_allowed_no_restrictions(self):
        """Test tool allowed with no restrictions."""
        config = AgentConfig(approval_mode=ApprovalMode.AUTO)

        # Any safe tool
        allowed, _ = config.is_tool_allowed("read_file", is_dangerous=False)
        assert allowed is True

        # Any dangerous tool
        allowed, _ = config.is_tool_allowed("execute_bash", is_dangerous=True)
        assert allowed is True
