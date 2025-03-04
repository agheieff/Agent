import os
import pytest
import tempfile
from Tools.File.edit import tool_edit, _ensure_absolute_path, EXAMPLES

class TestEditTool:
    @pytest.fixture
    def existing_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("Hello World\nMore lines")
            fname = tmp.name
        yield fname
        os.unlink(fname)

    def test_examples_dict(self):
        assert isinstance(EXAMPLES, dict)
        assert "file_path" in EXAMPLES
        assert isinstance(EXAMPLES["file_path"], str)
        assert "old" in EXAMPLES
        assert isinstance(EXAMPLES["old"], str)
        assert "new" in EXAMPLES
        assert isinstance(EXAMPLES["new"], str)

    def test_edit_unique_replacement(self, existing_file):
        result = tool_edit(file_path=existing_file, old="Hello World", new="Hello Universe")
        # Check that exit_code is 0 (success) and output indicates file was edited.
        assert result["exit_code"] == 0
        assert "Edited file:" in result["output"]
        with open(existing_file, "r") as f:
            content = f.read()
            assert "Hello Universe" in content

    def test_edit_no_such_file(self):
        result = tool_edit(file_path="/no/such/file.txt", old="abc", new="def")
        # Expect nonzero exit_code and error indicating file not found.
        assert result["exit_code"] != 0
        assert "File not found:" in result["error"]

    def test_edit_create_new_file_when_old_empty(self, tmp_path):
        new_file = os.path.join(tmp_path, "myfile.txt")
        result = tool_edit(file_path=new_file, old="", new="New content")
        assert result["exit_code"] == 0
        assert "Created new file:" in result["output"]
        with open(new_file, "r") as f:
            assert "New content" in f.read()

    def test_edit_multiple_occurrences(self, existing_file):
        # Append an extra occurrence of the target string.
        with open(existing_file, "a") as f:
            f.write("\nHello World")
        result = tool_edit(file_path=existing_file, old="Hello World", new="HELLO")
        # Expect failure due to multiple occurrences.
        assert result["exit_code"] != 0
        assert "appears 2 times" in result["error"]

    def test_edit_old_not_found(self, existing_file):
        result = tool_edit(file_path=existing_file, old="MissingString", new="X")
        # Expect failure when target string is not found.
        assert result["exit_code"] != 0
        assert "Target string not found" in result["error"]

    def test_ensure_absolute_path(self):
        rel = "some/rel/path"
        abs_p = _ensure_absolute_path(rel)
        assert os.path.isabs(abs_p)
