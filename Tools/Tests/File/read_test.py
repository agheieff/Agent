import os
import pytest
import tempfile
import asyncio
from Tools.File.read import tool_read, _is_binary_file, _ensure_absolute_path, EXAMPLES

class TestReadTool:
    @pytest.fixture
    def text_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            for i in range(1, 101):
                tmp.write(f"Line {i}\n")
            file_name = tmp.name
        yield file_name
        os.unlink(file_name)

    @pytest.fixture
    def binary_file(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
            tmp.write(b"Binary\x00Data\x00Here")
            file_name = tmp.name
        yield file_name
        os.unlink(file_name)

    def test_examples_dict(self):
        assert isinstance(EXAMPLES, dict)
        assert "file_path" in EXAMPLES
        assert isinstance(EXAMPLES["file_path"], str)
        assert "offset" in EXAMPLES
        assert isinstance(EXAMPLES["offset"], int)
        assert "limit" in EXAMPLES
        assert isinstance(EXAMPLES["limit"], int)

    @pytest.mark.asyncio
    async def test_read_file_success(self, text_file):
        result = await tool_read(file_path=text_file, offset=10, limit=5)
        # Expect success indicated by exit_code 0.
        assert result["exit_code"] == 0
        assert "Read 5 lines from" in result["output"]
        assert len(result["content"].splitlines()) == 5

    @pytest.mark.asyncio
    async def test_read_missing_file(self):
        result = await tool_read(file_path="/no/such/file")
        assert result["exit_code"] != 0
        assert "File not found:" in result["error"]

    @pytest.mark.asyncio
    async def test_read_directory(self, tmp_path):
        result = await tool_read(file_path=str(tmp_path))
        assert result["exit_code"] != 0
        assert "Path is a directory" in result["error"]

    @pytest.mark.asyncio
    async def test_read_binary_file(self, binary_file):
        result = await tool_read(file_path=binary_file)
        assert result["exit_code"] == 0
        assert "Binary file:" in result["output"]
        assert result.get("binary") is True

    @pytest.mark.asyncio
    async def test_negative_offset(self, text_file):
        result = await tool_read(file_path=text_file, offset=-1)
        assert result["exit_code"] != 0
        assert "Offset must be" in result["error"]

    def test_is_binary_file(self, binary_file, text_file):
        assert _is_binary_file(binary_file) is True
        assert _is_binary_file(text_file) is False

    def test_ensure_absolute_path(self):
        rel = "relative/path"
        abs_path = _ensure_absolute_path(rel)
        assert os.path.isabs(abs_path)
