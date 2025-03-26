# --- File: Tests/MCP/conftest.py ---

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path
from unittest.mock import patch
import copy
import logging

# --- Project Setup ---
# Ensure MCP module is importable by adding project root to sys.path
# Assumes conftest.py is in Tests/MCP/
root_dir = Path(__file__).parent.parent.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
# --- End Project Setup ---

# --- Imports (after path setup) ---
try:
    # Import the app *after* modifying sys.path
    from MCP.server import app as fastAPI_app
    # Import the original config and the variable name used in the module
    from MCP.permissions import DEFAULT_PERMISSIONS_CONFIG, PERMISSIONS_CONFIG as DYNAMIC_CONFIG_VAR_NAME
    CONFIG_MODULE_PATH = 'MCP.permissions.PERMISSIONS_CONFIG' # Path to patch
except ImportError as e:
    pytest.fail(f"Failed to import FastAPI app or PERMISSIONS_CONFIG: {e}\n"
                f"Ensure PYTHONPATH includes project root ({root_dir}) and MCP components exist.",
                pytrace=False)
except Exception as e:
     pytest.fail(f"An unexpected error occurred during import: {e}", pytrace=False)
# --- End Imports ---


logger = logging.getLogger(__name__)

# --- Fixtures ---

@pytest.fixture(scope="module")
def client():
    """Provides a FastAPI TestClient instance for the MCP server."""
    # TestClient handles lifespan events (startup/shutdown) automatically
    with TestClient(fastAPI_app) as test_client:
        logger.info("TestClient created for MCP app.")
        yield test_client
        logger.info("TestClient closing.")


@pytest.fixture
def test_payload_factory():
    """Factory fixture to create basic valid MCP request payloads."""
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
            "arguments": args if args is not None else {}, # Ensure 'arguments' key always exists
        }
        if agent is not None: # Allow explicitly passing agent=None
            payload["agent_id"] = agent
        return payload
    return _create_payload


@pytest.fixture(scope="function")
def agent_data_dir(tmp_path: Path):
    """
    Test fixture that:
    1. Creates a temporary 'agent_data' subdirectory within the test's tmp_path.
    2. Patches the `MCP.permissions.PERMISSIONS_CONFIG` dictionary for the
       duration of the test, replacing the hardcoded '/tmp/agent_data/' prefix
       in the 'tmp_readers_writers' group with the actual resolved path
       of the temporary directory created. This ensures file operations
       are correctly permissioned against the test's temporary space.

    Yields:
        Path: The resolved absolute path to the created temporary agent_data directory.
    """
    data_dir = tmp_path / "agent_data"
    data_dir.mkdir(exist_ok=True)
    resolved_data_dir = data_dir.resolve() # Get canonical path
    logger.debug(f"Created test agent_data_dir: {resolved_data_dir}")

    # --- Configuration Patching Logic ---
    # Deep copy the original default config to modify for patching
    patched_config = copy.deepcopy(DEFAULT_PERMISSIONS_CONFIG)

    # The specific hardcoded string prefix we want to replace in the config
    target_prefix_to_patch_str = "/tmp/agent_data/"
    # The dynamic path (as a string) to use in the patched config
    dynamic_path_prefix_str = str(resolved_data_dir) + "/" # Ensure trailing slash for prefix matching

    updated = False
    # Find and update the rule(s) in the 'tmp_readers_writers' group
    # This targets the specific group known to use the hardcoded path.
    tmp_rw_group = patched_config.get("groups", {}).get("tmp_readers_writers", {})
    if tmp_rw_group:
         for rule in tmp_rw_group.get("file_permissions", []):
             if rule.get("path_prefix") == target_prefix_to_patch_str:
                 rule["path_prefix"] = dynamic_path_prefix_str # Replace with resolved dynamic path string
                 updated = True
                 logger.debug(f"Patching rule in group 'tmp_readers_writers' to use prefix: {dynamic_path_prefix_str}")

    if not updated:
        # This warning is crucial if the base config structure/content changes.
        logger.warning(f"Could not find or patch rule matching exact string '{target_prefix_to_patch_str}' "
                       f"in group 'tmp_readers_writers' within PERMISSIONS_CONFIG. File permission tests might fail.")

    # Use patch context manager to temporarily replace the config in the permissions module.
    # CONFIG_MODULE_PATH ('MCP.permissions.PERMISSIONS_CONFIG') tells patch where the object lives.
    with patch(CONFIG_MODULE_PATH, patched_config):
        logger.debug(f"Applied patched PERMISSIONS_CONFIG targeting '{dynamic_path_prefix_str}' for test.")
        yield resolved_data_dir # Test runs here with the patched config

    # Patch is automatically reverted when the 'with' block exits.
    logger.debug(f"Restored original PERMISSIONS_CONFIG after test using {resolved_data_dir}")
    # --- End Patching Logic ---
