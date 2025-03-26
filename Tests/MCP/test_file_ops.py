import pytest
from fastapi.testclient import TestClient
import os
import stat # For checking permissions if needed, though less reliable across OS

# Define agents used in tests
AGENT_001 = "agent-001" # Has access to /tmp/agent_data/
AGENT_ADMIN = "agent-admin" # Has full access
AGENT_READONLY = "readonly-agent" # No file access by default config
AGENT_DEFAULT = None # Represents default permissions

# --- Read Tests ---
def test_read_file_success(client: TestClient, test_payload_factory, agent_data_dir):
    file_content = "Line 1\nLine 2\nLine 3"
    file = agent_data_dir / "read_test.txt"
    file.write_text(file_content, encoding='utf-8')

    payload = test_payload_factory("read_file", args={"path": str(file)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"content": file_content}
    assert data["id"] == payload["id"]

def test_read_file_specific_lines(client: TestClient, test_payload_factory, agent_data_dir):
    file_content = "L1\nL2\nL3\nL4"
    file = agent_data_dir / "read_lines.txt"
    file.write_text(file_content, encoding='utf-8')

    payload = test_payload_factory("read_file", args={"path": str(file), "lines": 2}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"content": "L1\nL2"}

def test_read_file_not_found(client: TestClient, test_payload_factory, agent_data_dir):
    payload = test_payload_factory("read_file", args={"path": str(agent_data_dir / "nonexistent.txt")}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 102 # RESOURCE_NOT_FOUND

def test_read_file_is_directory(client: TestClient, test_payload_factory, agent_data_dir):
    payload = test_payload_factory("read_file", args={"path": str(agent_data_dir)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 400 # Invalid argument (path is dir, not file)
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 11 # INVALID_ARGUMENTS

def test_read_file_permission_denied_agent(client: TestClient, test_payload_factory, tmp_path):
    # Create file outside the allowed agent_data_dir
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("Cannot read this", encoding='utf-8')

    # AGENT_001 only has tmp_readers_writers group, which is patched by agent_data_dir fixture
    # This path is OUTSIDE the patched directory, so permission should be denied.
    payload = test_payload_factory("read_file", args={"path": str(secret_file)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 403 # Permission Denied (Correct HTTP status for ErrorCode 13)
    data = response.json()
    assert data["status"] == "error"
    # --- FIX THE ASSERTION HERE ---
    assert data["error_code"] == 13 # PERMISSION_DENIED (raised by check_file_permission)
    # --- END FIX ---
    assert "Agent does not have 'read' permission" in data["message"] # Check message content


def test_read_file_permission_denied_os(client: TestClient, test_payload_factory, agent_data_dir):
    # Test OS-level permissions (might be OS specific)
    pytest.skip("OS-level permission tests can be OS-dependent and tricky.")
    # file = agent_data_dir / "unreadable.txt"
    # file.write_text("content")
    # os.chmod(str(file), 0o000) # No permissions
    # try:
    #     payload = test_payload_factory("read_file", args={"path": str(file)}, agent=AGENT_ADMIN) # Admin should pass agent check
    #     response = client.post("/mcp", json=payload)
    #     assert response.status_code == 403
    #     # Check for specific OS permission error code if defined (e.g., 101)
    # finally:
    #     os.chmod(str(file), 0o600) # Clean up permissions


# --- Write Tests ---
def test_write_file_success(client: TestClient, test_payload_factory, agent_data_dir):
    file_path = agent_data_dir / "write_test.txt"
    content = "New content to write"
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": content}, agent=AGENT_001)

    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert file_path.read_text(encoding='utf-8') == content
    assert data["result"]["path"] == str(file_path.absolute()) # Check absolute path in result
    assert data["result"]["bytes_written"] == len(content)

def test_write_file_permission_denied_agent(client: TestClient, test_payload_factory, tmp_path):
    # Try writing outside allowed directory
    file_path = tmp_path / "cannot_write_here.txt"
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": "test"}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 101 # PERMISSION_DENIED

def test_write_file_exists_no_overwrite(client: TestClient, test_payload_factory, agent_data_dir):
    file_path = agent_data_dir / "existing_write.txt"
    original_content = "Original Content"
    file_path.write_text(original_content, encoding='utf-8')
    # overwrite=False is default
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": "Attempted New"}, agent=AGENT_001)

    response = client.post("/mcp", json=payload)
    assert response.status_code == 409 # Conflict
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 103 # RESOURCE_EXISTS
    assert file_path.read_text(encoding='utf-8') == original_content # Verify content unchanged

def test_write_file_exists_with_overwrite(client: TestClient, test_payload_factory, agent_data_dir):
    file_path = agent_data_dir / "overwrite_target.txt"
    file_path.write_text("Old Stuff", encoding='utf-8')
    new_content = "Successfully Overwritten"
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": new_content, "overwrite": True}, agent=AGENT_001)

    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    assert file_path.read_text(encoding='utf-8') == new_content # Verify content changed


# --- Delete Tests ---
def test_delete_file_success(client: TestClient, test_payload_factory, agent_data_dir):
    file_path = agent_data_dir / "delete_me.txt"
    file_path.touch() # Create the file
    assert file_path.exists()
    payload = test_payload_factory("delete_file", args={"path": str(file_path)}, agent=AGENT_001)

    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["path"] == str(file_path.absolute())
    assert not file_path.exists() # Verify deleted

def test_delete_file_not_found(client: TestClient, test_payload_factory, agent_data_dir):
    file_path = agent_data_dir / "already_gone.txt"
    payload = test_payload_factory("delete_file", args={"path": str(file_path)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 102 # RESOURCE_NOT_FOUND

def test_delete_file_permission_denied_agent(client: TestClient, test_payload_factory, tmp_path):
    secret_file = tmp_path / "cannot_delete.txt"
    secret_file.touch()
    payload = test_payload_factory("delete_file", args={"path": str(secret_file)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 101 # PERMISSION_DENIED
    assert secret_file.exists() # Verify not deleted


# --- List Directory Tests ---
def test_list_directory_success(client: TestClient, test_payload_factory, agent_data_dir):
    (agent_data_dir / "fileA.txt").touch()
    (agent_data_dir / ".hidden").touch()
    (agent_data_dir / "subdirB").mkdir()

    payload = test_payload_factory("list_directory", args={"path": str(agent_data_dir)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["path"] == str(agent_data_dir.absolute())
    contents = data["result"]["contents"]
    # Sort by name for consistent comparison
    sorted_contents = sorted(contents, key=lambda x: x['name'])
    assert sorted_contents == [
        {'name': 'fileA.txt', 'type': 'file'},
        {'name': 'subdirB', 'type': 'directory'}
    ]

def test_list_directory_show_hidden(client: TestClient, test_payload_factory, agent_data_dir):
    (agent_data_dir / "fileA.txt").touch()
    (agent_data_dir / ".hidden").touch()
    (agent_data_dir / "subdirB").mkdir()

    payload = test_payload_factory("list_directory", args={"path": str(agent_data_dir), "show_hidden": True}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    sorted_contents = sorted(data["result"]["contents"], key=lambda x: x['name'])
    assert sorted_contents == [
        {'name': '.hidden', 'type': 'file'},
        {'name': 'fileA.txt', 'type': 'file'},
        {'name': 'subdirB', 'type': 'directory'}
    ]

def test_list_directory_permission_denied_agent(client: TestClient, test_payload_factory, tmp_path):
    # Try listing a directory the agent doesn't have list permission for
    payload = test_payload_factory("list_directory", args={"path": str(tmp_path)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 403
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 101 # PERMISSION_DENIED

def test_list_directory_not_a_directory(client: TestClient, test_payload_factory, agent_data_dir):
    file_path = agent_data_dir / "not_a_dir.txt"
    file_path.touch()
    payload = test_payload_factory("list_directory", args={"path": str(file_path)}, agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 11 # INVALID_ARGUMENTS
