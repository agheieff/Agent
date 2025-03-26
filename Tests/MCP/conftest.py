import pytest
from fastapi.testclient import TestClient
import sys, os

# Ensure MCP module is importable
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import the app *after* modifying sys.path
from MCP.server import app as fastAPI_app # Import your FastAPI app instance

@pytest.fixture(scope="module")
def client():
    """Provides a FastAPI TestClient instance."""
    with TestClient(fastAPI_app) as c:
        yield c

@pytest.fixture
def test_payload_factory():
    """Factory to create basic valid MCP request payloads."""
    def _create_payload(operation: str, args: dict = None, req_id: str = "test-req-123", agent: str = None):
        payload = {
            "mcp_version": "1.0",
            "type": "request",
            "id": req_id,
            "operation": operation,
            "arguments": args or {}
        }
        if agent:
             payload["agent_id"] = agent
        return payload
    return _create_payload

# Add fixtures for managing temporary files if needed (using pytest's tmp_path)
