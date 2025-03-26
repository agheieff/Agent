from fastapi.testclient import TestClient

def test_ping(client: TestClient, test_payload_factory):
    payload = test_payload_factory("ping")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == {"reply": "pong"}
    assert data["id"] == payload["id"]

def test_echo(client: TestClient, test_payload_factory):
    args = {"message": "Hello MCP!", "details": {"extra": 123}}
    payload = test_payload_factory("echo", args=args)
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["result"] == args # Echo should return the input args
    assert data["id"] == payload["id"]

def test_get_server_time(client: TestClient, test_payload_factory):
    payload = test_payload_factory("get_server_time")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "utc_time" in data["result"]
    # Add regex check for ISO format if needed
    assert data["id"] == payload["id"]

def test_list_operations_default(client: TestClient, test_payload_factory):
    # Assumes default agent can see echo, ping, list_operations, get_server_time
    payload = test_payload_factory("list_operations")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "operations" in data["result"]
    ops = {op["name"] for op in data["result"]["operations"]}
    assert "echo" in ops
    assert "ping" in ops
    assert "list_operations" in ops
    assert "get_server_time" in ops
    assert "read_file" not in ops # Default shouldn't see file ops

def test_list_operations_admin(client: TestClient, test_payload_factory):
    # Admin agent should see all discovered operations
    payload = test_payload_factory("list_operations", agent="agent-admin")
    response = client.post("/mcp", json=payload)
    assert response.status_code == 200
    data = response.json()
    ops = {op["name"] for op in data["result"]["operations"]}
    # Check for expected ops including file ops
    assert "read_file" in ops
    assert "write_file" in ops
    # ... add more checks based on discovered ops
