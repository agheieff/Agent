import os
import pytest
import tempfile
import asyncio
from Tools.File.write import tool_write, _ensure_absolute_path, EXAMPLES

class TestWriteTool:
    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        try:
            os.rmdir(d)
        except:
            pass

    def test_examples_dict(self):

        assert isinstance(EXAMPLES, dict)
        assert "file_path" in EXAMPLES
        assert isinstance(EXAMPLES["file_path"], str)
        assert "content" in EXAMPLES
        assert isinstance(EXAMPLES["content"], str)
        assert "mkdir" in EXAMPLES
        assert isinstance(EXAMPLES["mkdir"], bool)

    @pytest.mark.asyncio
    async def test_write_new_file(self, temp_dir):
        target_file = os.path.join(temp_dir, "newfile.txt")
        content = "Hello World"
        result = await tool_write(file_path=target_file, content=content)
        assert result["success"] is True
        assert os.path.exists(target_file)

    @pytest.mark.asyncio
    async def test_file_already_exists(self, temp_dir):
        fpath = os.path.join(temp_dir, "exists.txt")
        with open(fpath, "w") as f:
            f.write("Some content")

        result = await tool_write(file_path=fpath, content="New content")
        assert result["success"] is False
        assert "File already exists" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_file_path(self):
        result = await tool_write(file_path=None, content="Some content")
        assert result["success"] is False
        assert "Missing required parameter: file_path" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_content(self, temp_dir):
        fpath = os.path.join(temp_dir, "nocontent.txt")
        result = await tool_write(file_path=fpath, content=None)
        assert result["success"] is False
        assert "Missing required parameter: content" in result["error"]

    @pytest.mark.asyncio
    async def test_create_in_deep_dir(self, temp_dir):
        nested = os.path.join(temp_dir, "deep", "path", "file.txt")
        result = await tool_write(file_path=nested, content="Hello", mkdir=True)
        assert result["success"] is True
        assert os.path.exists(nested)


    def test_ensure_absolute_path(self):
        rel = "some/relative"
        abs_p = _ensure_absolute_path(rel)
        assert os.path.isabs(abs_p)
