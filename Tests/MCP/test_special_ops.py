from fastapi.testclient import TestClient
import datetime
import time

# Define agents used in tests
AGENT_001 = "agent-001"
AGENT_ADMIN = "agent-admin"
AGENT_DEFAULT = None

def test_ping(client: TestClient, test_payload_factory):
    """Tests the basic ping operation."""
    payload = test_payload_factory("ping", agent=AGENT_DEFAULT) # Should work for default agent
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"reply": "pong"}
    assert data["id"] == payload["id"]

def test_echo_success(client: TestClient, test_payload_factory):
    """Tests the echo operation with valid arguments."""
    args = {"message": "Testing echo!", "details": {"count": 5, "active": True}}
    payload = test_payload_factory("echo", args=args, agent=AGENT_001) # Should work for agent-001
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == args # Echo returns the exact arguments received
    assert data["id"] == payload["id"]

def test_echo_missing_required_arg(client: TestClient, test_payload_factory):
    """Tests echo when the required 'message' argument is missing."""
    payload = test_payload_factory("echo", args={}, agent=AGENT_001) # Missing 'message'
    response = client.post("/mcp", json=payload)
    assert response.status_code == 400 # Bad Request due to validation error
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 12 # VALIDATION_ERROR
    assert "message" in data["message"] # Error message should mention 'message' field

def test_get_server_time(client: TestClient, test_payload_factory):
    """Tests the get_server_time operation."""
    payload = test_payload_factory("get_server_time", agent=AGENT_001)
    before_ts = datetime.datetime.now(datetime.timezone.utc)
    time.sleep(0.01) # Small delay
    response = client.post("/mcp", json=payload)
    time.sleep(0.01)
    after_ts = datetime.datetime.now(datetime.timezone.utc)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "utc_time" in data["result"]
    try:
        # Attempt to parse the returned time string
        # Adjust format if GetServerTime uses a different one, but ISO 8601 with Z is good
        server_time_str = data["result"]["utc_time"]
        if server_time_str.endswith('Z'):
             server_time_str = server_time_str[:-1] + '+00:00' # datetime understands +00:00 better
        server_ts = datetime.datetime.fromisoformat(server_time_str)
        # Check if the server time is within the bounds of the test execution time
        assert before_ts <= server_ts <= after_ts
    except ValueError:
        pytest.fail(f"Could not parse server time string: {data['result']['utc_time']}")
    assert data["id"] == payload["id"]

def test_list_operations_default_agent(client: TestClient, test_payload_factory):
    """Tests list_operations for the default (None) agent."""
    payload = test_payload_factory("list_operations", agent=AGENT_DEFAULT)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "operations" in data["result"]
    ops = {op["name"] for op in data["result"]["operations"]}
    # Based on MCP/permissions.py default_permissions
    assert ops == {"echo", "ping", "list_operations", "get_server_time"}

def test_list_operations_agent_001(client: TestClient, test_payload_factory):
    """Tests list_operations for agent-001."""
    payload = test_payload_factory("list_operations", agent=AGENT_001)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    ops = {op["name"] for op in data["result"]["operations"]}
    # Based on groups default_user + tmp_readers_writers
    expected_ops = {
        "echo", "ping", "get_server_time", "list_operations",
        "read_file", "write_file", "delete_file", "list_directory"
    }
    assert ops == expected_ops

def test_list_operations_admin_agent(client: TestClient, test_payload_factory):
    """Tests list_operations for agent-admin (should see all)."""
    payload = test_payload_factory("list_operations", agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    ops = {op["name"] for op in data["result"]["operations"]}

    # Get all registered ops for comparison (requires registry access)
    # This makes the test dependent on the registry state, which is reasonable here.
    from MCP.registry import operation_registry
    all_registered_ops = set(operation_registry.get_all().keys())

    assert ops == all_registered_ops # Admin should see everything registered

def test_operation_permission_denied(client: TestClient, test_payload_factory):
    """Tests calling an operation the agent doesn't have permission for."""
    # agent-001 does *not* have '*' permission from default config
    # Try calling an operation only admin has implicitly (assuming no other groups grant it)
    # Let's assume 'read_file' requires tmp_readers_writers or admin group. Default agent doesn't have it.
    payload = test_payload_factory("read_file", args={"path": "/tmp/dummy"}, agent=AGENT_DEFAULT)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # Forbidden
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == 101 # PERMISSION_DENIED
    assert "does not have permission" in data["message"]
    assert "read_file" in data["message"]
