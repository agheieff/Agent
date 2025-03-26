import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import os
import stat # For potential OS permission tests

# Import error codes for clearer assertions
from MCP.errors import ErrorCode

# Define agents used in tests (consistent names)
AGENT_WITH_TMP_ACCESS = "agent-001" # Belongs to tmp_readers_writers group
AGENT_ADMIN = "agent-admin"         # Belongs to admin group (full access)
AGENT_READONLY_DOCS = "readonly-agent" # Belongs to doc_readers (read access to /shared/docs/)
AGENT_DEFAULT = None                # Represents default permissions (very limited)


# === Read Tests ===

def test_read_file_success(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify successful reading of a file within the allowed directory."""
    file_content = "Line 1\nLine 2\nLine 3"
    file = agent_data_dir / "read_test.txt"
    file.write_text(file_content, encoding='utf-8')

    payload = test_payload_factory("read_file", args={"path": str(file)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert data["result"] == {"content": file_content}


def test_read_file_specific_lines(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify reading only a specific number of lines."""
    file_content = "L1\nL2\nL3\nL4"
    file = agent_data_dir / "read_lines.txt"
    file.write_text(file_content, encoding='utf-8')

    payload = test_payload_factory("read_file", args={"path": str(file), "lines": 2}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"content": "L1\nL2"}


def test_read_file_lines_more_than_exists(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify reading lines stops correctly at EOF."""
    file_content = "Line A\nLine B"
    file = agent_data_dir / "read_short.txt"
    file.write_text(file_content, encoding='utf-8')

    payload = test_payload_factory("read_file", args={"path": str(file), "lines": 5}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"content": file_content}


def test_read_file_not_found(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when trying to read a non-existent file."""
    payload = test_payload_factory("read_file", args={"path": str(agent_data_dir / "nonexistent.txt")}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 404 # RESOURCE_NOT_FOUND maps to 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_NOT_FOUND


def test_read_file_is_directory(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when trying to read a directory as a file."""
    payload = test_payload_factory("read_file", args={"path": str(agent_data_dir)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # INVALID_ARGUMENTS maps to 400
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.INVALID_ARGUMENTS
    assert "Path is not a file" in data["message"]


def test_read_file_permission_denied_agent_config(client: TestClient, test_payload_factory, tmp_path: Path):
    """Verify permission denied when agent config doesn't allow reading the path."""
    # Create file outside the directory AGENT_WITH_TMP_ACCESS can access
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("Cannot read this", encoding='utf-8')

    # AGENT_WITH_TMP_ACCESS only has access to the dynamically patched agent_data_dir.
    # Accessing tmp_path itself should be denied by the check_file_permission logic.
    payload = test_payload_factory("read_file", args={"path": str(secret_file)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED maps to 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED
    assert "Agent lacks 'read' permission" in data["message"]


@pytest.mark.skipif(os.name == 'nt', reason="OS-level permission manipulation is complex and OS-dependent, skipping on Windows")
def test_read_file_permission_denied_os(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error due to underlying OS permissions, even if agent config allows."""
    unreadable_file = agent_data_dir / "unreadable.txt"
    unreadable_file.write_text("content")
    original_mode = unreadable_file.stat().st_mode
    # Remove read permission for everyone (owner, group, other)
    os.chmod(str(unreadable_file), 0o266) # Example: write only for owner

    # Use ADMIN agent who should pass agent config checks for this path
    payload = test_payload_factory("read_file", args={"path": str(unreadable_file)}, agent=AGENT_ADMIN)

    try:
        response = client.post("/mcp", json=payload)
        # Operation should raise MCPError(OS_PERMISSION_DENIED) which maps to 403
        assert response.status_code == 403
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == ErrorCode.OS_PERMISSION_DENIED
    finally:
        # Restore original permissions to allow cleanup by tmp_path fixture
         os.chmod(str(unreadable_file), original_mode)


# === Write Tests ===

def test_write_file_success_create(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify successful creation and writing to a new file."""
    file_path = agent_data_dir / "write_test_new.txt"
    content = "New content for a new file."
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": content}, agent=AGENT_WITH_TMP_ACCESS)

    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert file_path.is_file()
    assert file_path.read_text(encoding='utf-8') == content
    assert data["result"]["path"] == str(file_path.absolute())
    assert data["result"]["bytes_written"] == len(content)


def test_write_file_success_overwrite(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify successful overwriting of an existing file when overwrite=True."""
    file_path = agent_data_dir / "overwrite_target.txt"
    file_path.write_text("Old Stuff", encoding='utf-8')
    new_content = "Successfully Overwritten"
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": new_content, "overwrite": True}, agent=AGENT_WITH_TMP_ACCESS)

    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert file_path.read_text(encoding='utf-8') == new_content


def test_write_file_fail_exists_no_overwrite(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when file exists and overwrite is False (default)."""
    file_path = agent_data_dir / "existing_write_fail.txt"
    original_content = "Original Content - Do Not Overwrite"
    file_path.write_text(original_content, encoding='utf-8')

    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": "Attempted New Content"}, agent=AGENT_WITH_TMP_ACCESS) # overwrite=False is default

    response = client.post("/mcp", json=payload)

    assert response.status_code == 409 # RESOURCE_EXISTS maps to 409 Conflict
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_EXISTS
    # Verify content unchanged
    assert file_path.read_text(encoding='utf-8') == original_content


def test_write_file_permission_denied_agent_config(client: TestClient, test_payload_factory, tmp_path: Path):
    """Verify permission denied when agent config doesn't allow writing to the path."""
    # Try writing outside the allowed agent_data_dir
    disallowed_path = tmp_path / "cannot_write_here.txt"
    payload = test_payload_factory("write_file", args={"path": str(disallowed_path), "content": "test"}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED maps to 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED


def test_write_file_fail_parent_dir_not_exist(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when parent directory does not exist."""
    file_path = agent_data_dir / "nonexistent_subdir" / "file.txt"
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": "test"}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    # This fails because the parent dir doesn't exist during validation
    assert response.status_code == 404 # RESOURCE_NOT_FOUND (for parent dir) maps to 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_NOT_FOUND
    assert "Parent directory does not exist" in data["message"]


# === Delete Tests ===

def test_delete_file_success(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify successful deletion of a file."""
    file_path = agent_data_dir / "delete_me.txt"
    file_path.touch() # Create the file
    assert file_path.exists()

    payload = test_payload_factory("delete_file", args={"path": str(file_path)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert data["result"]["path"] == str(file_path.absolute())
    assert not file_path.exists() # Verify file is gone


def test_delete_file_not_found(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when trying to delete a non-existent file."""
    file_path = agent_data_dir / "already_gone.txt"
    assert not file_path.exists()

    payload = test_payload_factory("delete_file", args={"path": str(file_path)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 404 # RESOURCE_NOT_FOUND maps to 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_NOT_FOUND


def test_delete_file_permission_denied_agent_config(client: TestClient, test_payload_factory, tmp_path: Path):
    """Verify permission denied when agent config doesn't allow deleting the path."""
    secret_file = tmp_path / "cannot_delete.txt"
    secret_file.touch()
    payload = test_payload_factory("delete_file", args={"path": str(secret_file)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED maps to 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED
    assert secret_file.exists() # Verify file was not deleted


def test_delete_file_is_directory(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when trying to delete a directory using delete_file."""
    subdir_path = agent_data_dir / "subdir_to_delete"
    subdir_path.mkdir()
    payload = test_payload_factory("delete_file", args={"path": str(subdir_path)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # INVALID_ARGUMENTS maps to 400
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.INVALID_ARGUMENTS
    assert "Path is not a file" in data["message"]
    assert subdir_path.exists() # Verify directory was not deleted


# === List Directory Tests ===

def test_list_directory_success_basic(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify successful listing of directory contents (excluding hidden)."""
    (agent_data_dir / "fileA.txt").touch()
    (agent_data_dir / ".hiddenfile").touch()
    (agent_data_dir / "subdirB").mkdir()
    (agent_data_dir / ".hiddendir").mkdir()

    payload = test_payload_factory("list_directory", args={"path": str(agent_data_dir)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert data["result"]["path"] == str(agent_data_dir.absolute())

    contents = data["result"]["contents"]
    # Expected: directories first, then files, sorted alphabetically, excluding hidden
    expected_contents = [
        {'name': 'subdirB', 'type': 'directory'},
        {'name': 'fileA.txt', 'type': 'file'},
    ]
    # Sort actual results for consistent comparison if order isn't guaranteed by API
    # The operation itself sorts, so this might be redundant but safe
    sorted_contents = sorted(contents, key=lambda x: (x['type'] != 'directory', x['name'].lower()))
    assert sorted_contents == expected_contents


def test_list_directory_success_show_hidden(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify successful listing including hidden items when show_hidden=True."""
    (agent_data_dir / "fileA.txt").touch()
    (agent_data_dir / ".hiddenfile").touch()
    (agent_data_dir / "subdirB").mkdir()
    (agent_data_dir / ".hiddendir").mkdir()

    payload = test_payload_factory("list_directory", args={"path": str(agent_data_dir), "show_hidden": True}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

    contents = data["result"]["contents"]
    expected_contents = [
        {'name': '.hiddendir', 'type': 'directory'},
        {'name': 'subdirB', 'type': 'directory'},
        {'name': '.hiddenfile', 'type': 'file'},
        {'name': 'fileA.txt', 'type': 'file'},
    ]
    # Sort actual results using the same logic as the operation
    sorted_contents = sorted(contents, key=lambda x: (x['type'] != 'directory', x['name'].lower()))
    assert sorted_contents == expected_contents


def test_list_directory_permission_denied_agent_config(client: TestClient, test_payload_factory, tmp_path: Path):
    """Verify permission denied when agent config doesn't allow listing the path."""
    # tmp_path itself is outside the agent's allowed /tmp/agent_data/ prefix
    payload = test_payload_factory("list_directory", args={"path": str(tmp_path)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED maps to 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED


def test_list_directory_not_a_directory(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when trying to list a file path instead of a directory."""
    file_path = agent_data_dir / "not_a_dir.txt"
    file_path.touch()
    payload = test_payload_factory("list_directory", args={"path": str(file_path)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # INVALID_ARGUMENTS maps to 400
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.INVALID_ARGUMENTS
    assert "Path is not a directory" in data["message"]


def test_list_directory_not_found(client: TestClient, test_payload_factory, agent_data_dir: Path):
    """Verify error when trying to list a non-existent directory."""
    dir_path = agent_data_dir / "nonexistent_dir"
    payload = test_payload_factory("list_directory", args={"path": str(dir_path)}, agent=AGENT_WITH_TMP_ACCESS)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 404 # RESOURCE_NOT_FOUND maps to 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.RESOURCE_NOT_FOUND
