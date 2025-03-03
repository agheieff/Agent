import os
import shutil
import pytest
import tempfile
import asyncio
from typing import Dict, Any


from Tools.File.write import tool_write, _ensure_absolute_path

class TestWriteTool:

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir

        shutil.rmtree(temp_dir)

    @pytest.fixture
    def existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as temp:
            temp.write("Existing content")
            temp_name = temp.name


        yield temp_name


        os.unlink(temp_name)

    @pytest.fixture
    def nonexistent_deep_path(self, temp_dir):
        return os.path.join(temp_dir, "deep", "nested", "path", "file.txt")

    @pytest.mark.asyncio
    async def test_help_parameter(self):
        result = await tool_write(help=True)

        assert result["success"] is True
        assert result["error"] == ""
        assert "Create a new file with the specified content" in result["output"]
        assert "Examples:" in result["output"]

    @pytest.mark.asyncio
    async def test_create_file(self, temp_dir):
        file_path = os.path.join(temp_dir, "test.txt")
        content = "Hello, world!"

        result = await tool_write(file_path=file_path, content=content)

        assert result["success"] is True
        assert result["error"] == ""
        assert "Created file:" in result["output"]
        assert f"Size: {len(content)} bytes" in result["output"]
        assert "Lines: 1" in result["output"]


        assert os.path.exists(file_path)
        with open(file_path, 'r') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_create_file_with_multiline_content(self, temp_dir):
        file_path = os.path.join(temp_dir, "multiline.txt")
        content = "Line 1\nLine 2\nLine 3\n"

        result = await tool_write(file_path=file_path, content=content)

        assert result["success"] is True
        assert result["error"] == ""
        assert "Created file:" in result["output"]
        assert f"Size: {len(content)} bytes" in result["output"]
        assert "Lines: 4" in result["output"]                              


        assert os.path.exists(file_path)
        with open(file_path, 'r') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_create_in_nonexistent_directory_with_mkdir(self, nonexistent_deep_path):
        content = "Content in deep directory"

        result = await tool_write(file_path=nonexistent_deep_path, content=content, mkdir=True)

        assert result["success"] is True
        assert result["error"] == ""
        assert "Created file:" in result["output"]


        assert os.path.exists(nonexistent_deep_path)
        with open(nonexistent_deep_path, 'r') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_create_in_nonexistent_directory_without_mkdir(self, nonexistent_deep_path):
        content = "Content in deep directory"

        result = await tool_write(file_path=nonexistent_deep_path, content=content, mkdir=False)

        assert result["success"] is False
        assert "Parent directory does not exist" in result["error"]
        assert not os.path.exists(nonexistent_deep_path)

    @pytest.mark.asyncio
    async def test_file_already_exists(self, existing_file):
        content = "New content"

        result = await tool_write(file_path=existing_file, content=content)

        assert result["success"] is False
        assert "File already exists" in result["error"]


        with open(existing_file, 'r') as f:
            assert f.read() == "Existing content"

    @pytest.mark.asyncio
    async def test_missing_file_path(self):
        result = await tool_write(content="Content without file path")

        assert result["success"] is False
        assert result["error"] == "Missing required parameter: file_path"
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_missing_content(self):
        result = await tool_write(file_path="/tmp/test.txt")

        assert result["success"] is False
        assert result["error"] == "Missing required parameter: content"
        assert result["output"] == ""

    @pytest.mark.asyncio
    async def test_positional_parameter(self, temp_dir):
        file_path = os.path.join(temp_dir, "positional.txt")
        content = "Content via positional parameter"

        result = await tool_write(value=file_path, content=content)

        assert result["success"] is True
        assert "Created file:" in result["output"]
        assert os.path.exists(file_path)
        with open(file_path, 'r') as f:
            assert f.read() == content

    @pytest.mark.asyncio
    async def test_positional_parameter_in_kwargs(self, temp_dir):
        file_path = os.path.join(temp_dir, "kwargs_positional.txt")
        content = "Content via kwargs positional parameter"

        result = await tool_write(**{"0": file_path, "content": content})

        assert result["success"] is True
        assert "Created file:" in result["output"]
        assert os.path.exists(file_path)
        with open(file_path, 'r') as f:
            assert f.read() == content

    def test_ensure_absolute_path(self):

        abs_path = "/absolute/path/to/file.txt"
        assert _ensure_absolute_path(abs_path) == abs_path


        rel_path = "relative/path/to/file.txt"
        abs_result = _ensure_absolute_path(rel_path)
        assert os.path.isabs(abs_result)
        assert abs_result.endswith(rel_path)


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
