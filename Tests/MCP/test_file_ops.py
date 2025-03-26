# Tests/MCP/test_file_ops.py
import pytest
from fastapi.testclient import TestClient
import os

# --- Read Tests ---
def test_read_file_success(client: TestClient, test_payload_factory, tmp_path):
    file_content = "Line 1\nLine 2\nLine 3"
    file = tmp_path / "read_test.txt"
    file.write_text(file_content)
    payload = test_payload_factory("read_file", args={"path": str(file)}, agent="agent-001") # Use agent with /tmp/ access

    # Create the agent_data directory if your permissions require it
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    file_in_agent_dir = agent_data_dir / "read_test.txt"
    file_in_agent_dir.write_text(file_content)
    payload_agent_dir = test_payload_factory("read_file", args={"path": str(file_in_agent_dir)}, agent="agent-001")


    response = client.post("/mcp", json=payload_agent_dir)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"content": file_content}

def test_read_file_not_found(client: TestClient, test_payload_factory, tmp_path):
    payload = test_payload_factory("read_file", args={"path": str(tmp_path / "nonexistent.txt")}, agent="agent-001")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 404 # Or as mapped by server
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 102 # RESOURCE_NOT_FOUND

def test_read_file_permission_denied_agent(client: TestClient, test_payload_factory, tmp_path):
    file = tmp_path / "secret.txt"
    file.write_text("secret data") # File outside allowed /tmp/agent_data/
    payload = test_payload_factory("read_file", args={"path": str(file)}, agent="agent-001") # agent-001 can only access /tmp/agent_data
    response = client.post("/mcp", json=payload)
    assert response.status_code == 403 # Permission denied
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 101 # PERMISSION_DENIED

# --- Write Tests ---
def test_write_file_success(client: TestClient, test_payload_factory, tmp_path):
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    file_path = agent_data_dir / "write_test.txt"
    content = "New content"
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": content}, agent="agent-001")

    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert file_path.read_text() == content
    assert data["result"]["path"] == str(file_path)

def test_write_file_exists_no_overwrite(client: TestClient, test_payload_factory, tmp_path):
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    file_path = agent_data_dir / "existing.txt"
    file_path.write_text("Original")
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": "New"}, agent="agent-001") # overwrite=False by default

    response = client.post("/mcp", json=payload)
    assert response.status_code == 409 # Conflict
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 103 # RESOURCE_EXISTS
    assert file_path.read_text() == "Original" # Check content wasn't changed

def test_write_file_exists_with_overwrite(client: TestClient, test_payload_factory, tmp_path):
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    file_path = agent_data_dir / "overwrite_me.txt"
    file_path.write_text("Old")
    payload = test_payload_factory("write_file", args={"path": str(file_path), "content": "New", "overwrite": True}, agent="agent-001")

    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    assert file_path.read_text() == "New" # Check content was changed

# --- Delete Tests ---
def test_delete_file_success(client: TestClient, test_payload_factory, tmp_path):
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    file_path = agent_data_dir / "delete_me.txt"
    file_path.touch()
    assert file_path.exists()
    payload = test_payload_factory("delete_file", args={"path": str(file_path)}, agent="agent-001")

    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert not file_path.exists()

# --- List Directory Tests ---
def test_list_directory_success(client: TestClient, test_payload_factory, tmp_path):
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    (agent_data_dir / "file1.txt").touch()
    (agent_data_dir / ".hiddenfile").touch()
    (agent_data_dir / "subdir").mkdir()

    payload = test_payload_factory("list_directory", args={"path": str(agent_data_dir)}, agent="agent-001")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    contents = data["result"]["contents"]
    names = {item["name"] for item in contents}
    assert names == {"file1.txt", "subdir"} # Hidden file excluded by default

def test_list_directory_show_hidden(client: TestClient, test_payload_factory, tmp_path):
    agent_data_dir = tmp_path / "agent_data"
    agent_data_dir.mkdir(exist_ok=True)
    (agent_data_dir / "file1.txt").touch()
    (agent_data_dir / ".hiddenfile").touch()

    payload = test_payload_factory("list_directory", args={"path": str(agent_data_dir), "show_hidden": True}, agent="agent-001")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    names = {item["name"] for item in data["result"]["contents"]}
    assert names == {"file1.txt", ".hiddenfile"}

# Add more tests for server errors, edge cases, permissions etc.
