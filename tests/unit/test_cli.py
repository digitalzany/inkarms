"""
Unit tests for CLI commands.
"""

from typer.testing import CliRunner

from inkarms import __version__
from inkarms.cli.app import app


def test_version(cli_runner: CliRunner) -> None:
    """Test --version flag."""
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help(cli_runner: CliRunner) -> None:
    """Test --help flag."""
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "inkarms" in result.stdout
    assert "run" in result.stdout
    assert "config" in result.stdout
    assert "skill" in result.stdout


def test_run_without_query(cli_runner: CliRunner) -> None:
    """Test run command without query shows error."""
    result = cli_runner.invoke(app, ["run"])
    assert result.exit_code == 1
    assert "Query is required" in result.stdout


def test_run_with_query(cli_runner: CliRunner) -> None:
    """Test run command with query shows model being used."""
    result = cli_runner.invoke(app, ["run", "test query"])
    # Should show the model being used (even if API fails due to no key)
    assert "Model:" in result.stdout or "Authentication" in result.stdout


def test_run_dry_run(cli_runner: CliRunner) -> None:
    """Test run command with --dry-run flag."""
    result = cli_runner.invoke(app, ["run", "--dry-run", "test query"])
    assert result.exit_code == 0
    assert "Dry Run" in result.stdout
    assert "test query" in result.stdout


def test_config_show(cli_runner: CliRunner) -> None:
    """Test config show command (placeholder)."""
    result = cli_runner.invoke(app, ["config", "show"])
    # Should not crash, placeholder message expected
    assert result.exit_code == 0


def test_skill_list(cli_runner: CliRunner) -> None:
    """Test skill list command (placeholder)."""
    result = cli_runner.invoke(app, ["skill", "list"])
    # Should not crash, placeholder message expected
    assert result.exit_code == 0


def test_status(cli_runner: CliRunner) -> None:
    """Test status command (placeholder)."""
    result = cli_runner.invoke(app, ["status"])
    # Should not crash, placeholder message expected
    assert result.exit_code == 0


def test_profile_list(cli_runner: CliRunner) -> None:
    """Test profile list command (placeholder)."""
    result = cli_runner.invoke(app, ["profile", "list"])
    # Should not crash, placeholder message expected
    assert result.exit_code == 0


def test_memory_list(cli_runner: CliRunner) -> None:
    """Test memory list command (placeholder)."""
    result = cli_runner.invoke(app, ["memory", "list"])
    # Should not crash, placeholder message expected
    assert result.exit_code == 0


def test_audit_tail(cli_runner: CliRunner) -> None:
    """Test audit tail command (placeholder)."""
    result = cli_runner.invoke(app, ["audit", "tail"])
    # Should not crash, placeholder message expected
    assert result.exit_code == 0
