import os
import pytest
import tempfile
import asyncio
from typing import Dict, Any

from Tools.File.read import tool_read, _is_binary_file, _ensure_absolute_path

class TestReadTool:
    @pytest.fixture
    def text_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as temp:
            for i in range(1, 101):
                temp.write(f"Line {i}\n")
            temp_name = temp.name
        yield temp_name
        os.unlink(temp_name)

    @pytest.fixture
    def binary_file(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".bin") as temp:
            temp.write(b"Binary\x00Data\x00With\x00Null\x00Bytes")
            temp_name = temp.name
        yield temp_name
        os.unlink(temp_name)

    @pytest.fixture
    def nonexistent_file(self):
        return "/path/to/nonexistent/file.txt"

    @pytest.fixture
    def directory(self):
        return tempfile.gettempdir()

    @pytest.mark.asyncio
    async def test_help_parameter(self):
        result = await tool_read(help=True)
        assert result["success"] is True
        assert result["error"] == ""
        assert "Read the contents of a file" in result["output"]
        assert "Examples:" in result["output"]

    @pytest.mark.asyncio
    async def test_view_text_file(self, text_file):
        result = await tool_read(file_path=text_file)
        assert result["success"] is True
        assert result["error"] == ""
        assert "File:" in result["output"]
        assert "Line 1" in result["output"]
        assert "Showing 100 lines" in result["output"]
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_view_binary_file(self, binary_file):
        result = await tool_read(file_path=binary_file)
        assert result["success"] is True
        assert result["error"] == ""
        assert "Binary file:" in result["output"]

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, nonexistent_file):
        result = await tool_read(file_path=nonexistent_file)
        assert result["success"] is False
        assert "File not found:" in result["error"]
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_directory(self, directory):
        result = await tool_read(file_path=directory)
        assert result["success"] is False
        assert "Path is a directory:" in result["error"]
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_missing_file_path(self):
        result = await tool_read()
        assert result["success"] is False
        assert result["error"] == "Missing required parameter: file_path"
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_offset_and_limit(self, text_file):
        result = await tool_read(file_path=text_file, offset=10, limit=5)
        assert result["success"] is True
        assert result["error"] == ""
        assert "Starting from line: 11" in result["output"]
        assert "Showing 5 lines" in result["output"]
        assert "Line 11" in result["output"]
        assert "Line 15" in result["output"]
        assert "Line 16" not in result["output"]
        assert result["offset"] == 10
        assert result["limit"] == 5
        assert result["truncated"] is True

    @pytest.mark.asyncio
    async def test_offset_exceeds_file_length(self, text_file):
        result = await tool_read(file_path=text_file, offset=200)
        assert result["success"] is True
        assert result["error"] == ""
        assert "Starting from line: 201" in result["output"]
        assert "Showing 0 lines" in result["output"]
        assert result["lines_read"] == 0

    @pytest.mark.asyncio
    async def test_negative_offset(self, text_file):
        result = await tool_read(file_path=text_file, offset=-10)
        assert result["success"] is False
        assert "Offset must be a non-negative integer" in result["error"]
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_invalid_offset(self, text_file):
        result = await tool_read(file_path=text_file, offset="not-a-number")
        assert result["success"] is False
        assert "Offset must be a valid integer" in result["error"]
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_zero_limit(self, text_file):
        result = await tool_read(file_path=text_file, limit=0)
        assert result["success"] is False
        assert "Limit must be a positive integer" in result["error"]
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_invalid_limit(self, text_file):
        result = await tool_read(file_path=text_file, limit="not-a-number")
        assert result["success"] is False
        assert "Limit must be a valid integer" in result["error"]
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_positional_parameter(self, text_file):
        result = await tool_read(value=text_file)
        assert result["success"] is True
        assert "File:" in result["output"]
        assert "Line 1" in result["output"]

    @pytest.mark.asyncio
    async def test_positional_parameter_in_kwargs(self, text_file):
        result = await tool_read(**{"0": text_file})
        assert result["success"] is True
        assert "File:" in result["output"]
        assert "Line 1" in result["output"]

    def test_is_binary_file(self, binary_file, text_file):
        assert _is_binary_file(binary_file) is True
        assert _is_binary_file(text_file) is False

    def test_ensure_absolute_path(self):
        abs_path = "/absolute/path/to/file.txt"
        assert _ensure_absolute_path(abs_path) == abs_path
        rel_path = "relative/path/to/file.txt"
        abs_result = _ensure_absolute_path(rel_path)
        assert os.path.isabs(abs_result)
        assert abs_result.endswith(rel_path)

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
