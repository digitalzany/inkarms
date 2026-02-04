"""Tests for built-in file operation tools."""

import pytest
from pathlib import Path

from inkarms.tools.builtin.file import ListFilesTool, ReadFileTool, WriteFileTool


class TestReadFileTool:
    """Tests for ReadFileTool."""

    def test_tool_properties(self):
        """Test tool basic properties."""
        tool = ReadFileTool()

        assert tool.name == "read_file"
        assert "Read" in tool.description
        assert tool.is_dangerous is False

        params = {p.name: p for p in tool.parameters}
        assert "path" in params
        assert params["path"].required is True
        assert "encoding" in params
        assert params["encoding"].required is False

    @pytest.mark.asyncio
    async def test_read_file_success(self, tmp_path):
        """Test successful file read."""
        tool = ReadFileTool()

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Read file
        result = await tool.execute(path=str(test_file), tool_call_id="call_123")

        assert result.tool_call_id == "call_123"
        assert result.is_error is False
        assert "Hello, World!" in result.output
        assert str(test_file) in result.output

    @pytest.mark.asyncio
    async def test_read_file_not_found(self, tmp_path):
        """Test reading non-existent file."""
        tool = ReadFileTool()

        result = await tool.execute(
            path=str(tmp_path / "nonexistent.txt"), tool_call_id="call_123"
        )

        assert result.is_error is True
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_directory(self, tmp_path):
        """Test reading a directory fails."""
        tool = ReadFileTool()

        result = await tool.execute(path=str(tmp_path), tool_call_id="call_123")

        assert result.is_error is True
        assert "not a file" in result.error.lower()

    @pytest.mark.asyncio
    async def test_read_with_encoding(self, tmp_path):
        """Test reading file with specific encoding."""
        tool = ReadFileTool()

        # Create file with UTF-8 encoding
        test_file = tmp_path / "test.txt"
        test_file.write_text("Ünïcödé", encoding="utf-8")

        # Read with UTF-8
        result = await tool.execute(
            path=str(test_file), encoding="utf-8", tool_call_id="call_123"
        )

        assert result.is_error is False
        assert "Ünïcödé" in result.output


class TestWriteFileTool:
    """Tests for WriteFileTool."""

    def test_tool_properties(self):
        """Test tool basic properties."""
        tool = WriteFileTool()

        assert tool.name == "write_file"
        assert "Write" in tool.description
        assert tool.is_dangerous is True  # Write is dangerous

        params = {p.name: p for p in tool.parameters}
        assert "path" in params
        assert "content" in params
        assert params["path"].required is True
        assert params["content"].required is True

    @pytest.mark.asyncio
    async def test_write_file_success(self, tmp_path):
        """Test successful file write."""
        tool = WriteFileTool()

        test_file = tmp_path / "output.txt"

        result = await tool.execute(
            path=str(test_file), content="Test content", tool_call_id="call_123"
        )

        assert result.is_error is False
        assert "output.txt" in result.output
        assert test_file.exists()
        assert test_file.read_text() == "Test content"

    @pytest.mark.asyncio
    async def test_write_file_overwrite(self, tmp_path):
        """Test overwriting existing file."""
        tool = WriteFileTool()

        test_file = tmp_path / "output.txt"
        test_file.write_text("Old content")

        result = await tool.execute(
            path=str(test_file), content="New content", tool_call_id="call_123"
        )

        assert result.is_error is False
        assert test_file.read_text() == "New content"

    @pytest.mark.asyncio
    async def test_write_file_no_parent_dir(self, tmp_path):
        """Test writing to non-existent parent directory."""
        tool = WriteFileTool()

        test_file = tmp_path / "nonexistent" / "output.txt"

        result = await tool.execute(
            path=str(test_file), content="Test", tool_call_id="call_123"
        )

        assert result.is_error is True
        assert "does not exist" in result.error.lower()

    @pytest.mark.asyncio
    async def test_write_file_create_dirs(self, tmp_path):
        """Test writing with create_dirs option."""
        tool = WriteFileTool()

        test_file = tmp_path / "new_dir" / "output.txt"

        result = await tool.execute(
            path=str(test_file),
            content="Test",
            create_dirs=True,
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert test_file.exists()
        assert test_file.read_text() == "Test"

    @pytest.mark.asyncio
    async def test_write_with_encoding(self, tmp_path):
        """Test writing file with specific encoding."""
        tool = WriteFileTool()

        test_file = tmp_path / "unicode.txt"

        result = await tool.execute(
            path=str(test_file),
            content="Ünïcödé",
            encoding="utf-8",
            tool_call_id="call_123",
        )

        assert result.is_error is False
        assert test_file.read_text(encoding="utf-8") == "Ünïcödé"


class TestListFilesTool:
    """Tests for ListFilesTool."""

    def test_tool_properties(self):
        """Test tool basic properties."""
        tool = ListFilesTool()

        assert tool.name == "list_files"
        assert "List" in tool.description
        assert tool.is_dangerous is False

        params = {p.name: p for p in tool.parameters}
        assert "path" in params
        assert "recursive" in params
        assert "show_hidden" in params

    @pytest.mark.asyncio
    async def test_list_files_success(self, tmp_path):
        """Test successful directory listing."""
        tool = ListFilesTool()

        # Create test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file3.txt").write_text("content3")

        result = await tool.execute(path=str(tmp_path), tool_call_id="call_123")

        assert result.is_error is False
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
        assert "subdir" in result.output
        # Should not show files in subdirectory without recursive
        assert "file3.txt" not in result.output

    @pytest.mark.asyncio
    async def test_list_files_recursive(self, tmp_path):
        """Test recursive directory listing."""
        tool = ListFilesTool()

        # Create nested structure
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.txt").write_text("content2")
        (tmp_path / "subdir" / "nested").mkdir()
        (tmp_path / "subdir" / "nested" / "file3.txt").write_text("content3")

        result = await tool.execute(
            path=str(tmp_path), recursive=True, tool_call_id="call_123"
        )

        assert result.is_error is False
        assert "file1.txt" in result.output
        assert "file2.txt" in result.output
        assert "file3.txt" in result.output

    @pytest.mark.asyncio
    async def test_list_files_hidden(self, tmp_path):
        """Test listing hidden files."""
        tool = ListFilesTool()

        # Create files
        (tmp_path / "visible.txt").write_text("content")
        (tmp_path / ".hidden.txt").write_text("content")

        # Without show_hidden
        result1 = await tool.execute(path=str(tmp_path), tool_call_id="call_123")
        assert "visible.txt" in result1.output
        assert ".hidden.txt" not in result1.output

        # With show_hidden
        result2 = await tool.execute(
            path=str(tmp_path), show_hidden=True, tool_call_id="call_123"
        )
        assert "visible.txt" in result2.output
        assert ".hidden.txt" in result2.output

    @pytest.mark.asyncio
    async def test_list_files_not_found(self, tmp_path):
        """Test listing non-existent directory."""
        tool = ListFilesTool()

        result = await tool.execute(
            path=str(tmp_path / "nonexistent"), tool_call_id="call_123"
        )

        assert result.is_error is True
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_files_not_directory(self, tmp_path):
        """Test listing a file instead of directory."""
        tool = ListFilesTool()

        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        result = await tool.execute(path=str(test_file), tool_call_id="call_123")

        assert result.is_error is True
        assert "not a directory" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_files_size_formatting(self, tmp_path):
        """Test file size formatting in output."""
        tool = ListFilesTool()

        # Create files of different sizes
        (tmp_path / "small.txt").write_text("x" * 100)  # < 1KB
        (tmp_path / "medium.txt").write_text("x" * 2048)  # ~2KB
        (tmp_path / "large.txt").write_text("x" * (1024 * 1024 * 2))  # 2MB

        result = await tool.execute(path=str(tmp_path), tool_call_id="call_123")

        assert result.is_error is False
        assert "B" in result.output  # Bytes
        assert "KB" in result.output  # Kilobytes
        assert "MB" in result.output  # Megabytes
