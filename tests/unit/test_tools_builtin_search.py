"""Tests for built-in search tool."""

import pytest
from pathlib import Path

from inkarms.tools.builtin.search import SearchFilesTool


class TestSearchFilesTool:
    """Tests for SearchFilesTool."""

    def test_tool_properties(self):
        """Test tool basic properties."""
        tool = SearchFilesTool()

        assert tool.name == "search_files"
        assert "Search" in tool.description
        assert tool.is_dangerous is False

        params = {p.name: p for p in tool.parameters}
        assert "path" in params
        assert "pattern" in params
        assert "content_search" in params
        assert "case_sensitive" in params
        assert "file_pattern" in params
        assert "max_results" in params

        assert params["pattern"].required is True
        assert params["path"].required is False

    @pytest.mark.asyncio
    async def test_search_filenames_glob(self, tmp_path):
        """Test searching files by glob pattern."""
        tool = SearchFilesTool()

        # Create test files
        (tmp_path / "test1.py").write_text("content")
        (tmp_path / "test2.py").write_text("content")
        (tmp_path / "test.txt").write_text("content")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "test3.py").write_text("content")

        # Search for Python files
        result = await tool.execute(
            path=str(tmp_path),
            pattern="*.py",
            content_search=False,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "test1.py" in result.output
        assert "test2.py" in result.output
        assert "test3.py" in result.output  # Recursive by default
        assert "test.txt" not in result.output

    @pytest.mark.asyncio
    async def test_search_filenames_no_results(self, tmp_path):
        """Test filename search with no results."""
        tool = SearchFilesTool()

        (tmp_path / "test.txt").write_text("content")

        result = await tool.execute(
            path=str(tmp_path),
            pattern="*.py",
            content_search=False,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "No results found" in result.output

    @pytest.mark.asyncio
    async def test_search_content_simple(self, tmp_path):
        """Test searching file content."""
        tool = SearchFilesTool()

        # Create test files
        (tmp_path / "file1.txt").write_text("Hello World\nFoo Bar")
        (tmp_path / "file2.txt").write_text("Goodbye World\nBaz")
        (tmp_path / "file3.txt").write_text("Nothing here")

        # Search for "World"
        result = await tool.execute(
            path=str(tmp_path),
            pattern="World",
            content_search=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
        assert "file3.txt" not in result.output
        assert "Hello World" in result.output

    @pytest.mark.asyncio
    async def test_search_content_case_sensitive(self, tmp_path):
        """Test case-sensitive content search."""
        tool = SearchFilesTool()

        (tmp_path / "file1.txt").write_text("HELLO world")
        (tmp_path / "file2.txt").write_text("hello WORLD")

        # Case-insensitive (default)
        result1 = await tool.execute(
            path=str(tmp_path),
            pattern="hello",
            content_search=True,
            case_sensitive=False,
            tool_call_id="call_123",
        )

        assert "file1.txt" in result1.output
        assert "file2.txt" in result1.output

        # Case-sensitive
        result2 = await tool.execute(
            path=str(tmp_path),
            pattern="hello",
            content_search=True,
            case_sensitive=True,
            tool_call_id="call_123",
        )

        assert "file1.txt" not in result2.output
        assert "file2.txt" in result2.output

    @pytest.mark.asyncio
    async def test_search_content_with_file_pattern(self, tmp_path):
        """Test content search filtered by file pattern."""
        tool = SearchFilesTool()

        # Create files
        (tmp_path / "test.py").write_text("def hello():\n    pass")
        (tmp_path / "test.txt").write_text("hello world")
        (tmp_path / "test.md").write_text("# Hello")

        # Search only Python files
        result = await tool.execute(
            path=str(tmp_path),
            pattern="hello",
            content_search=True,
            file_pattern="*.py",
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "test.py" in result.output
        assert "test.txt" not in result.output
        assert "test.md" not in result.output

    @pytest.mark.asyncio
    async def test_search_content_regex(self, tmp_path):
        """Test regex pattern in content search."""
        tool = SearchFilesTool()

        (tmp_path / "file1.txt").write_text("function_name_1\nfunction_name_2")
        (tmp_path / "file2.txt").write_text("variable_name")

        # Regex pattern
        result = await tool.execute(
            path=str(tmp_path),
            pattern=r"function_name_\d+",
            content_search=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "file1.txt" in result.output
        assert "function_name_1" in result.output
        assert "file2.txt" not in result.output

    @pytest.mark.asyncio
    async def test_search_content_max_results(self, tmp_path):
        """Test max results limit."""
        tool = SearchFilesTool()

        # Create many files with same content
        for i in range(20):
            (tmp_path / f"file{i}.txt").write_text("target")

        # Search with limit
        result = await tool.execute(
            path=str(tmp_path),
            pattern="target",
            content_search=True,
            max_results=5,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        # Should have exactly 5 results
        lines = [l for l in result.output.split("\n") if "file" in l and ".txt" in l]
        assert len(lines) == 5

    @pytest.mark.asyncio
    async def test_search_content_skips_binary_files(self, tmp_path):
        """Test that binary files are skipped."""
        tool = SearchFilesTool()

        # Create text file
        (tmp_path / "text.txt").write_text("hello world")

        # Create binary-like file (with null bytes)
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"hello\x00world")

        result = await tool.execute(
            path=str(tmp_path),
            pattern="hello",
            content_search=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "text.txt" in result.output
        # Binary file should be skipped
        assert "binary.bin" not in result.output

    @pytest.mark.asyncio
    async def test_search_content_skips_hidden_dirs(self, tmp_path):
        """Test that hidden directories are skipped."""
        tool = SearchFilesTool()

        # Create regular file
        (tmp_path / "visible.txt").write_text("hello")

        # Create file in hidden directory
        hidden_dir = tmp_path / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "file.txt").write_text("hello")

        # Create file in node_modules
        node_dir = tmp_path / "node_modules"
        node_dir.mkdir()
        (node_dir / "file.txt").write_text("hello")

        result = await tool.execute(
            path=str(tmp_path),
            pattern="hello",
            content_search=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "visible.txt" in result.output
        # Hidden directory files should be skipped
        assert ".hidden" not in result.output
        assert "node_modules" not in result.output

    @pytest.mark.asyncio
    async def test_search_path_not_found(self, tmp_path):
        """Test search with non-existent directory."""
        tool = SearchFilesTool()

        result = await tool.execute(
            path=str(tmp_path / "nonexistent"),
            pattern="*.py",
            tool_call_id="call_123",
        )

        assert result.is_error is True
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_path_not_directory(self, tmp_path):
        """Test search on a file instead of directory."""
        tool = SearchFilesTool()

        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = await tool.execute(
            path=str(test_file), pattern="*.py", tool_call_id="call_123"
        )

        assert result.is_error is True
        assert "not a directory" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_content_line_numbers(self, tmp_path):
        """Test that content search includes line numbers."""
        tool = SearchFilesTool()

        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2 target\nline3\nline4 target")

        result = await tool.execute(
            path=str(tmp_path),
            pattern="target",
            content_search=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert "test.txt:2:" in result.output  # Line 2
        assert "test.txt:4:" in result.output  # Line 4

    @pytest.mark.asyncio
    async def test_search_content_line_truncation(self, tmp_path):
        """Test that long lines are truncated in output."""
        tool = SearchFilesTool()

        # Create file with very long line
        long_line = "x" * 200 + " target " + "y" * 200
        (tmp_path / "test.txt").write_text(long_line)

        result = await tool.execute(
            path=str(tmp_path),
            pattern="target",
            content_search=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        # Should be truncated to ~100 chars
        lines = [l for l in result.output.split("\n") if "test.txt:" in l]
        assert len(lines) > 0
        # Line preview should be truncated (exact length may vary)
        assert len(lines[0]) < 150  # Much shorter than original 400+ chars

    @pytest.mark.asyncio
    async def test_search_filename_shows_type(self, tmp_path):
        """Test that filename search shows file type."""
        tool = SearchFilesTool()

        (tmp_path / "file.txt").write_text("content")
        (tmp_path / "subdir").mkdir()

        result = await tool.execute(
            path=str(tmp_path), pattern="*", tool_call_id="call_123"
        )

        assert result.is_error is False
        assert "FILE" in result.output
        assert "DIR" in result.output

    def test_input_validation_missing_pattern(self):
        """Test validation fails without pattern."""
        tool = SearchFilesTool()

        with pytest.raises(ValueError, match="Missing required parameters: pattern"):
            tool.validate_input(path="/tmp")

    def test_input_validation_unknown_param(self):
        """Test validation fails with unknown parameter."""
        tool = SearchFilesTool()

        with pytest.raises(ValueError, match="Unknown parameters"):
            tool.validate_input(pattern="test", unknown_param="value")
