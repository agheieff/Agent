# File: /Tests/MCP/test_special_ops.py

import pytest
from fastapi.testclient import TestClient
import datetime
import time
import math # For tolerant time comparison

# Import error codes for clearer assertions
from MCP.errors import ErrorCode

# Define agents used in tests
AGENT_001 = "agent-001"
AGENT_ADMIN = "agent-admin"
AGENT_DEFAULT = None # Represents default permissions


def test_ping_success(client: TestClient, test_payload_factory):
    """Tests the basic ping operation, should work for any allowed agent (including default)."""
    payload = test_payload_factory("ping", agent=AGENT_DEFAULT)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert data["result"] == {"reply": "pong"}


def test_echo_success_simple(client: TestClient, test_payload_factory):
    """Tests echo with just the required message argument."""
    args = {"message": "Hello, Echo!"}
    payload = test_payload_factory("echo", args=args, agent=AGENT_001) # Agent 001 has echo permission
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    # Echo returns the exact validated arguments received by the operation
    assert data["result"] == {"message": "Hello, Echo!", "details": {}} # Default for details is {}


def test_echo_success_with_details(client: TestClient, test_payload_factory):
    """Tests echo with both message and optional details arguments."""
    args = {"message": "Testing echo details", "details": {"count": 5, "active": True, "items": [1, "b"]}}
    payload = test_payload_factory("echo", args=args, agent=AGENT_001)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert data["result"] == args # Echo returns the exact arguments


def test_echo_fail_missing_required_arg(client: TestClient, test_payload_factory):
    """Tests echo failure when the required 'message' argument is missing."""
    payload = test_payload_factory("echo", args={"details": {"info": "only details"}}, agent=AGENT_001) # Missing 'message'
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # Validation Error maps to 400
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.VALIDATION_ERROR
    # Ensure the error details point to the missing 'message' field
    assert any(err.get('loc') and 'message' in err['loc'] for err in data.get("details", [])), "Error details should mention missing 'message'"


def test_get_server_time_success(client: TestClient, test_payload_factory):
    """Tests the get_server_time operation returns a valid UTC timestamp."""
    payload = test_payload_factory("get_server_time", agent=AGENT_001) # Agent 001 has permission

    # Get current UTC time just before and after the request for comparison
    before_ts_utc = datetime.datetime.now(datetime.timezone.utc)
    time.sleep(0.01) # Small delay
    response = client.post("/mcp", json=payload)
    time.sleep(0.01)
    after_ts_utc = datetime.datetime.now(datetime.timezone.utc)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert "utc_time" in data["result"]

    server_time_str = data["result"]["utc_time"]
    try:
        # Attempt to parse the returned ISO 8601 string
        # fromisoformat handles timezone offsets like Z or +00:00 correctly
        server_ts_utc = datetime.datetime.fromisoformat(server_time_str)

        # Verify the timestamp is timezone-aware and represents UTC
        assert server_ts_utc.tzinfo is not None
        assert server_ts_utc.tzinfo.utcoffset(server_ts_utc) == datetime.timedelta(0)

        # Check if the server time is within a reasonable window around the test execution time
        # Use a tolerance (e.g., 1 second) to account for network/processing delays
        tolerance_seconds = 1.5 # Slightly increased tolerance for CI environments
        assert before_ts_utc <= server_ts_utc <= after_ts_utc + datetime.timedelta(seconds=tolerance_seconds), \
                f"Server time {server_time_str} out of expected range ({before_ts_utc.isoformat()} to {after_ts_utc.isoformat()})"

    except ValueError as e:
        pytest.fail(f"Could not parse server time string '{server_time_str}' as ISO 8601 UTC: {e}")
    except Exception as e:
        pytest.fail(f"Error during timestamp comparison: {e}")


def test_list_operations_default_agent(client: TestClient, test_payload_factory):
    """Tests list_operations for the default agent, showing only limited default ops."""
    payload = test_payload_factory("list_operations", agent=AGENT_DEFAULT)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "operations" in data["result"]
    ops_list = data["result"]["operations"]
    ops_names = {op["name"] for op in ops_list}

    # Based on MCP/permissions.py default_permissions
    # Note: Default permissions might vary based on your config. This matches the provided default.
    expected_ops = {"echo", "ping", "list_operations"}
    assert ops_names == expected_ops
    # Optionally check argument definitions format for one operation
    ping_op = next((op for op in ops_list if op["name"] == "ping"), None)
    assert ping_op is not None
    assert ping_op["description"] == "A simple health check operation that returns 'pong'."
    assert ping_op["arguments"] == []


def test_list_operations_agent_001(client: TestClient, test_payload_factory):
    """Tests list_operations for agent-001, showing combined group permissions."""
    payload = test_payload_factory("list_operations", agent=AGENT_001)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    ops_names = {op["name"] for op in data["result"]["operations"]}

    # Based on groups: default_user + tmp_readers_writers
    # Check MCP/permissions.py for the exact definition
    expected_ops = {
        "echo", "ping", "get_server_time", "list_operations", # From default_user
        "read_file", "write_file", "delete_file", "list_directory", # From tmp_readers_writers
        "finish_goal" # From tmp_readers_writers
    }
    assert ops_names == expected_ops


def test_list_operations_admin_agent(client: TestClient, test_payload_factory):
    """Tests list_operations for admin agent, should show all registered operations."""
    payload = test_payload_factory("list_operations", agent=AGENT_ADMIN)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    ops_names = {op["name"] for op in data["result"]["operations"]}

    # Get all registered ops dynamically for comparison
    # Ensure registry is loaded (should be by TestClient lifespan)
    from MCP.registry import operation_registry
    all_registered_ops_names = set(operation_registry.get_all().keys())

    # Make sure the registry actually found operations before asserting
    assert len(all_registered_ops_names) > 0, "Operation registry appears empty during test."

    assert ops_names == all_registered_ops_names # Admin ('*') should see everything registered


def test_operation_permission_denied_for_agent(client: TestClient, test_payload_factory):
    """Tests calling an operation the agent doesn't have permission for based on agent config."""
    # AGENT_DEFAULT does *not* have permission for 'read_file' based on default config.
    payload = test_payload_factory("read_file", args={"path": "/tmp/dummy"}, agent=AGENT_DEFAULT)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED maps to 403
    data = response.json()
    assert data["status"] == "error"
    # Server permission check for the operation *itself* happens before execution
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED
    assert "lacks permission for operation" in data["message"]
    assert "read_file" in data["message"]


# --- Tests for finish_goal ---

def test_finish_goal_success(client: TestClient, test_payload_factory):
    """Tests successful call to finish_goal by an allowed agent."""
    summary_text = "Successfully read the input and wrote the summary."
    args = {"summary": summary_text}
    # Agent 001 is in tmp_readers_writers group which has finish_goal permission
    payload = test_payload_factory("finish_goal", args=args, agent=AGENT_001)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["id"] == payload["id"]
    assert data["result"] == {"message": "Goal completion signaled.", "summary": summary_text}
    # NOTE: The AgentRunner outside the test would actually stop the loop here.


def test_finish_goal_permission_denied(client: TestClient, test_payload_factory):
    """Tests that an agent without permission cannot call finish_goal."""
    args = {"summary": "Trying to finish"}
    # AGENT_DEFAULT does not have finish_goal permission
    payload = test_payload_factory("finish_goal", args=args, agent=AGENT_DEFAULT)
    response = client.post("/mcp", json=payload)

    assert response.status_code == 403 # PERMISSION_DENIED
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.PERMISSION_DENIED
    assert "lacks permission for operation 'finish_goal'" in data["message"]


def test_finish_goal_missing_summary(client: TestClient, test_payload_factory):
    """Tests failure when the required 'summary' argument is missing."""
    payload = test_payload_factory("finish_goal", args={}, agent=AGENT_001) # Missing 'summary'
    response = client.post("/mcp", json=payload)

    assert response.status_code == 400 # Validation Error
    data = response.json()
    assert data["status"] == "error"
    assert data["error_code"] == ErrorCode.VALIDATION_ERROR
    assert any(err.get('loc') and 'summary' in err['loc'] for err in data.get("details", [])), "Error details should mention missing 'summary'"
