# --- File: MCP/permissions.py ---

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import copy # For deep copying config during patching in tests

logger = logging.getLogger(__name__)

# --- Configuration ---
# Load from file (YAML/JSON) in production. Hardcoded here for simplicity.
# IMPORTANT: Path normalization (resolve()) is crucial for security when checking prefixes.
# The check_file_permission function performs this normalization.

DEFAULT_PERMISSIONS_CONFIG = {
    "agents": {
        "agent-001": {
            "id": "agent-001",
            "description": "Standard agent with limited file access",
            "groups": ["default_user", "tmp_readers_writers"]
        },
        "agent-admin": {
            "id": "agent-admin",
            "description": "Admin agent with full access",
            "groups": ["admin"]
        },
        "readonly-agent": {
            "id": "readonly-agent",
            "description": "Agent that can only read certain files",
            "groups": ["default_user", "doc_readers"]
        }
    },
    "groups": {
        "default_user": {
            "allowed_operations": [
                "echo",
                "ping",
                "get_server_time",
                "list_operations" # Allow seeing available ops they have access to
            ],
            "file_permissions": [] # No file access by default
        },
        "tmp_readers_writers": {
            "allowed_operations": [ # Grant specific file op permissions
                "read_file",
                "write_file",
                "delete_file",
                "list_directory"
            ],
            "file_permissions": [
                # Allows R/W/D/L within /tmp/agent_data/ (or OS equivalent).
                # Path resolve() handles variations.
                # **NOTE**: This exact string "/tmp/agent_data/" is patched in tests.
                {"path_prefix": "/tmp/agent_data/", "permissions": ["read", "write", "delete", "list"]}
            ]
        },
         "doc_readers": {
            "allowed_operations": [
                "read_file",
                "list_directory"
            ],
            "file_permissions": [
                {"path_prefix": "/shared/docs/", "permissions": ["read", "list"]}
            ]
        },
        "admin": {
            "allowed_operations": ["*"], # Wildcard grants all operations
            "file_permissions": [
                # Grants full R/W/D/L access from root. Use with extreme caution!
                {"path_prefix": "/", "permissions": ["read", "write", "delete", "list"]}
            ]
        },
    },
    # Default permissions applied if agent_id is None or not found in 'agents'
    "default_permissions": {
        "allowed_operations": ["echo", "ping", "list_operations"], # Very limited
        "file_permissions": []
    }
}

# Use a variable that can be patched by tests
PERMISSIONS_CONFIG = copy.deepcopy(DEFAULT_PERMISSIONS_CONFIG)


# --- Helper Functions ---

def _resolve_groups(agent_id: Optional[str], config: Dict) -> Set[str]:
    """Finds all groups an agent belongs to based on the provided config."""
    agent_conf = config.get("agents", {}).get(agent_id) if agent_id else None
    return set(agent_conf.get("groups", [])) if agent_conf else set()


def get_agent_permissions(agent_id: Optional[str]) -> Dict[str, Any]:
    """
    Calculates the effective permissions for an agent by merging permissions
    from all groups they belong to. Handles wildcard '*' for operations.
    Uses the current state of the global PERMISSIONS_CONFIG.
    """
    # Use the current global config (which might be patched in tests)
    current_config = PERMISSIONS_CONFIG

    if not agent_id or agent_id not in current_config.get("agents", {}):
        logger.debug(f"Agent ID '{agent_id}' not found or None, using default permissions.")
        # Return a copy to prevent modification of the original default config
        return current_config.get("default_permissions", {}).copy()

    agent_groups = _resolve_groups(agent_id, current_config)
    if not agent_groups:
         logger.warning(f"Agent '{agent_id}' found but belongs to no groups. Using default permissions.")
         return current_config.get("default_permissions", {}).copy()

    # Combine permissions from all assigned groups
    effective_allowed_ops: Set[str] = set()
    effective_file_perms: List[Dict] = []

    for group_name in agent_groups:
        group_conf = current_config.get("groups", {}).get(group_name, {})
        if not group_conf:
             logger.warning(f"Agent '{agent_id}' belongs to group '{group_name}' which is not defined in config.")
             continue

        effective_allowed_ops.update(group_conf.get("allowed_operations", []))
        effective_file_perms.extend(group_conf.get("file_permissions", []))

    # Handle wildcard '*' in operations - if present, it grants all ops.
    final_allowed_ops = ["*"] if "*" in effective_allowed_ops else sorted(list(effective_allowed_ops))

    effective_permissions = {
        "agent_id": agent_id,
        "groups": sorted(list(agent_groups)),
        "allowed_operations": final_allowed_ops,
        "file_permissions": effective_file_perms # Pass all rules; checking logic finds the best match
    }
    logger.debug(f"Effective permissions calculated for agent '{agent_id}': {effective_permissions}")
    return effective_permissions


def check_file_permission(
    requested_path_str: str,
    required_permission: str, # e.g., "read", "write", "delete", "list"
    file_permission_rules: List[Dict]
) -> bool:
    """
    Checks if the required permission is granted for the requested path based
    on the agent's merged file permission rules. Uses pathlib.Path.resolve()
    for robust path normalization and finds the most specific matching rule.

    Args:
        requested_path_str: The file or directory path requested by the operation.
        required_permission: The permission being checked ('read', 'write', etc.).
        file_permission_rules: List of rule dictionaries [{'path_prefix': str, 'permissions': List[str]}].

    Returns:
        True if permission is granted, False otherwise.
    """
    if not requested_path_str:
        logger.debug("Permission check denied: Requested path is empty.")
        return False

    # --- Path Resolution ---
    # Resolve the requested path to get a canonical absolute path.
    # This handles '..', symlinks (by default), and OS-specific separators.
    # We resolve *before* checking rules to ensure consistent comparisons.
    try:
        # Use strict=False initially to allow checking permissions on potentially
        # non-existent paths (e.g., for a 'write' operation).
        # We still need to handle errors if the path is fundamentally invalid.
        resolved_req_path = Path(requested_path_str).resolve(strict=False)
    except Exception as e:
        # Catch errors during resolution (e.g., path too long, invalid characters)
        logger.warning(f"Permission check denied: Could not resolve requested path '{requested_path_str}': {e}")
        return False
    # --- End Path Resolution ---


    best_match_rule = None
    longest_prefix_len = -1

    for rule in file_permission_rules:
        rule_path_prefix_str = rule.get("path_prefix")
        if not rule_path_prefix_str:
            continue # Skip rules without a path_prefix

        try:
            # Resolve the rule prefix path as well for consistent comparison.
            # Assume rule paths should generally exist. Use strict=False for flexibility?
            resolved_rule_path = Path(rule_path_prefix_str).resolve(strict=False)
            current_prefix_len = len(str(resolved_rule_path))

            # Check if the resolved requested path IS or IS WITHIN the resolved rule path.
            # Path.is_relative_to() is available in Python 3.9+ and is cleaner:
            # if resolved_req_path.is_relative_to(resolved_rule_path): ...
            # Fallback for < 3.9:
            is_match = (resolved_req_path == resolved_rule_path or
                        resolved_rule_path in resolved_req_path.parents)

            if is_match:
                 # Find the *most specific* rule (longest path prefix) that applies.
                if current_prefix_len > longest_prefix_len:
                    longest_prefix_len = current_prefix_len
                    best_match_rule = rule
                # TODO: Add precedence logic here if needed (e.g., deny rules override allow rules).
                # For now, the longest prefix wins.

        except Exception as e:
            logger.warning(f"Permission check skipped invalid rule: Could not resolve rule path '{rule_path_prefix_str}': {e}")
            continue # Skip invalid rules

    # --- Check Permissions of Best Match ---
    is_allowed = False
    matched_prefix_debug = "None"
    if best_match_rule:
        matched_prefix_debug = best_match_rule.get('path_prefix', 'Error')
        allowed_perms_for_rule = best_match_rule.get("permissions", [])
        if required_permission in allowed_perms_for_rule:
            is_allowed = True
    # --- End Check ---

    logger.debug(
        f"Permission check: req='{requested_path_str}' (resolved='{resolved_req_path}'), "
        f"perm='{required_permission}', "
        f"best_match_prefix='{matched_prefix_debug}', "
        f"rules_checked={len(file_permission_rules)}, "
        f"allowed={is_allowed}"
    )
    return is_allowed
