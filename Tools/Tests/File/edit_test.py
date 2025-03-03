import os
import tempfile
import shutil
import pytest
from Tools.File.edit import tool_edit, _ensure_absolute_path

class TestEditTool:

    @pytest.fixture
    def temp_dir(self):
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def existing_file(self, temp_dir):
        file_path = os.path.join(temp_dir, "existing.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("Hello World\nThis is a test.\nAnother line.")
        return file_path

    @pytest.mark.asyncio
    async def test_help_parameter(self):
        result = tool_edit(help=True)
        assert result["success"] is True
        assert "Edit a file by replacing a specific string" in result["output"]

    @pytest.mark.asyncio
    async def test_unique_replacement(self, existing_file):
        result = tool_edit(file_path=existing_file, old="Hello World", new="Hello Universe")
        assert result["success"] is True
        assert "Successfully edited file:" in result["output"]
        with open(existing_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Hello Universe" in content
            assert "Hello World" not in content

    @pytest.mark.asyncio
    async def test_nonexistent_file_with_old_non_empty(self, temp_dir):
        file_path = os.path.join(temp_dir, "no_such.txt")
        result = tool_edit(file_path=file_path, old="something", new="anything")
        assert result["success"] is False
        assert "File not found:" in result["error"]

    @pytest.mark.asyncio
    async def test_create_new_file_with_old_empty(self, temp_dir):
        file_path = os.path.join(temp_dir, "brand_new.txt")
        result = tool_edit(file_path=file_path, old="", new="New content for brand new file.")
        assert result["success"] is True
        assert "Created new file:" in result["output"]
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "New content for brand new file." in content

    @pytest.mark.asyncio
    async def test_multiline_replacement(self, existing_file):

        with open(existing_file, "w", encoding="utf-8") as f:
            f.write("""class Foo:
    def bar(self):
        pass
""")


        old_text = """class Foo:
    def bar(self):
        pass
"""
        new_text = """class Foo:
    def bar(self):
        print("Updated!")
"""
        result = tool_edit(file_path=existing_file, old=old_text, new=new_text)
        assert result["success"] is True
        with open(existing_file, "r", encoding="utf-8") as f:
            replaced_content = f.read()
            assert "print(\"Updated!\")" in replaced_content

    def test_ensure_absolute_path(self):
        abs_path = "/absolute/path/to/file.txt"
        assert _ensure_absolute_path(abs_path) == abs_path
        rel_path = "relative/path/to/file.txt"
        abs_result = _ensure_absolute_path(rel_path)
        assert os.path.isabs(abs_result)
        assert abs_result.endswith(rel_path)
