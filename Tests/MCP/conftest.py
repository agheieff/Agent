import pytest
from fastapi.testclient import TestClient
import sys, os
from pathlib import Path # Import Path

# Ensure MCP module is importable by adding project root to sys.path
# Adjust depth as necessary based on where tests are run from
root_dir = Path(__file__).parent.parent.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Import the app *after* modifying sys.path
# This assumes MCP/server.py defines 'app = FastAPI()'
try:
    from MCP.server import app as fastAPI_app
except ImportError as e:
    pytest.fail(f"Failed to import FastAPI app from MCP.server: {e}\nEnsure PYTHONPATH includes project root and MCP/server.py defines 'app'.")


@pytest.fixture(scope="module")
def client():
    """Provides a FastAPI TestClient instance for the MCP server."""
    # Ensure operations are discovered before tests run (if startup event doesn't run in test client scope)
    # from MCP.registry import operation_registry
    # if not operation_registry.get_all(): # Check if already discovered
    #     operation_registry.discover_operations()

    with TestClient(fastAPI_app) as c:
        yield c

@pytest.fixture
def test_payload_factory():
    """Factory to create basic valid MCP request payloads."""
    req_counter = 0
    def _create_payload(operation: str, args: dict = None, req_id: str = None, agent: str = None):
        nonlocal req_counter
        req_counter += 1
        _req_id = req_id or f"test-req-{req_counter}"
        payload = {
            "mcp_version": "1.0",
            "type": "request",
            "id": _req_id,
            "operation": operation,
            "arguments": args if args is not None else {} # Ensure arguments is always present
        }
        if agent:
             payload["agent_id"] = agent
        return payload
    return _create_payload

# Optional fixture to manage the /tmp/agent_data directory for tests
@pytest.fixture(scope="function") # Use function scope to ensure clean state per test
def agent_data_dir(tmp_path):
    """Creates and returns the path to a temporary agent_data directory."""
    data_dir = tmp_path / "agent_data"
    data_dir.mkdir(exist_ok=True)
    # You might want to set permissions here if relevant to tests,
    # though tmp_path usually handles this well.
    return data_dir
