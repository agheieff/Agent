import pytest
from fastapi.testclient import TestClient
import sys, os
from pathlib import Path # Import Path
from unittest.mock import patch # Import patch
import copy # Import copy

# Ensure MCP module is importable by adding project root to sys.path
# Adjust depth as necessary based on where tests are run from
root_dir = Path(__file__).parent.parent.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Import the app *after* modifying sys.path
# This assumes MCP/server.py defines 'app = FastAPI()'
try:
    from MCP.server import app as fastAPI_app
    # Import the original config *after* ensuring MCP is in path
    from MCP.permissions import PERMISSIONS_CONFIG
except ImportError as e:
    pytest.fail(f"Failed to import FastAPI app or PERMISSIONS_CONFIG: {e}\nEnsure PYTHONPATH includes project root and MCP/server.py/permissions.py exist.")
except Exception as e:
     pytest.fail(f"An unexpected error occurred during import: {e}")

@pytest.fixture(scope="module")
def client():
    """Provides a FastAPI TestClient instance for the MCP server."""
    # Startup event should run automatically with TestClient
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

# Updated fixture to manage the /tmp/agent_data directory AND patch permissions
@pytest.fixture(scope="function")
def agent_data_dir(tmp_path):
    """
    Creates a temporary agent_data directory AND patches the
    PERMISSIONS_CONFIG to use this dynamic path for the test duration,
    using pathlib.Path.resolve() for robust path handling.
    """
    data_dir = tmp_path / "agent_data"
    data_dir.mkdir(exist_ok=True)
    resolved_data_dir = data_dir.resolve() # Resolve once
    print(f"Created test agent_data_dir: {resolved_data_dir}") # Debug print

    # --- Patching Logic ---
    original_config = copy.deepcopy(PERMISSIONS_CONFIG) # Keep a clean copy
    patched_config = copy.deepcopy(PERMISSIONS_CONFIG)

    # The specific string prefix we want to replace in the config
    target_prefix_to_patch_str = "/tmp/agent_data/"

    # Use the dynamically created and resolved data_dir path as a string for the new rule value
    dynamic_path_prefix_str = str(resolved_data_dir) # String representation for JSON-like config

    updated = False
    # Find and update the relevant rule(s) in the copied config
    for group, config in patched_config.get("groups", {}).items():
        for rule in config.get("file_permissions", []):
            rule_prefix_str = rule.get("path_prefix")
            # Compare the original rule string directly
            if rule_prefix_str == target_prefix_to_patch_str:
                rule["path_prefix"] = dynamic_path_prefix_str # Replace with the resolved dynamic path string
                updated = True
                print(f"Patching rule in group '{group}' to use prefix: {dynamic_path_prefix_str}") # Debug print

    if not updated:
        # This warning helps catch issues if the base config changes
        print(f"Warning: Did not find or patch rule matching exact string '{target_prefix_to_patch_str}' in PERMISSIONS_CONFIG.")

    # Use patch context manager to apply the change for the test's duration
    # The string 'MCP.permissions.PERMISSIONS_CONFIG' tells patch where to find the object to replace.
    with patch('MCP.permissions.PERMISSIONS_CONFIG', patched_config):
        print(f"Applied patched PERMISSIONS_CONFIG targeting '{dynamic_path_prefix_str}'") # Debug print
        yield resolved_data_dir # The test runs here with the patched config and resolved path

    # --- End Patching Logic ---
    # Patch is automatically reverted after yield
    print(f"Restored original PERMISSIONS_CONFIG after test using {resolved_data_dir}") # Debug print
