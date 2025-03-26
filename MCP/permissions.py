# MCP/permissions.py
import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# --- Configuration ---
# Define permissions here directly as a Python dictionary for simplicity.
# Replace with YAML/JSON loading for more complex setups.

PERMISSIONS_CONFIG = {
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
        # Add more agents as needed
    },
    "groups": {
        "default_user": {
            "allowed_operations": [
                "echo",
                "ping",
                "get_server_time",
                "list_operations" # Allow seeing available ops
            ],
            "file_permissions": [] # No default file access
        },
        "tmp_readers_writers": {
             "allowed_operations": [ # Allow file ops for this group
                 "read_file",
                 "write_file",
                 "delete_file",
                 "list_directory"
             ],
            "file_permissions": [
                {"path_prefix": "/tmp/agent_data/", "permissions": ["read", "write", "delete", "list"]}
                # Note: Using path_prefix for basic check. Real systems need more robust path handling.
            ]
        },
        "admin": {
            "allowed_operations": ["*"], # Wildcard for all operations
            "file_permissions": [
                 {"path_prefix": "/", "permissions": ["read", "write", "delete", "list"]} # Full access
            ]
        },
        # Add more groups as needed
    },
    "default_permissions": { # Applied if agent_id is None or not found
        "allowed_operations": ["echo", "ping", "list_operations"],
        "file_permissions": []
    }
}

# --- Helper Functions ---

def _resolve_groups(agent_id: Optional[str]) -> Set[str]:
    """Find all groups an agent belongs to."""
    agent_conf = PERMISSIONS_CONFIG["agents"].get(agent_id) if agent_id else None
    if agent_conf:
        return set(agent_conf.get("groups", []))
    return set()

def get_agent_permissions(agent_id: Optional[str]) -> Dict:
    """
    Calculates the effective permissions for a given agent ID by merging
    their direct permissions (if any) and group permissions.
    """
    if not agent_id or agent_id not in PERMISSIONS_CONFIG["agents"]:
        logger.debug(f"Agent ID '{agent_id}' not found or not provided, using default permissions.")
        return PERMISSIONS_CONFIG["default_permissions"]

    agent_conf = PERMISSIONS_CONFIG["agents"][agent_id]
    agent_groups = _resolve_groups(agent_id)

    # Combine allowed operations from all groups
    effective_allowed_ops: Set[str] = set()
    # Start with agent's direct permissions if defined (not used in current config)
    # effective_allowed_ops.update(agent_conf.get("allowed_operations", []))

    for group_name in agent_groups:
        group_conf = PERMISSIONS_CONFIG["groups"].get(group_name, {})
        effective_allowed_ops.update(group_conf.get("allowed_operations", []))

    # Combine file permissions (simple list concatenation for now)
    effective_file_perms: List[Dict] = []
    # Start with agent's direct permissions if defined (not used in current config)
    # effective_file_perms.extend(agent_conf.get("file_permissions", []))

    for group_name in agent_groups:
        group_conf = PERMISSIONS_CONFIG["groups"].get(group_name, {})
        effective_file_perms.extend(group_conf.get("file_permissions", []))

    # Handle wildcard '*' in operations
    final_allowed_ops = ["*"] if "*" in effective_allowed_ops else list(effective_allowed_ops)


    effective_permissions = {
        "agent_id": agent_id,
        "groups": list(agent_groups),
        "allowed_operations": final_allowed_ops,
        "file_permissions": effective_file_perms
    }
    logger.debug(f"Effective permissions for agent '{agent_id}': {effective_permissions}")
    return effective_permissions


def check_file_permission(
    requested_path: str,
    required_permission: str, # e.g., "read", "write", "delete", "list"
    file_permission_rules: List[Dict]
) -> bool:
    """
    Checks if the required permission is granted for the requested path
    based on the agent's file permission rules.

    VERY BASIC IMPLEMENTATION using prefix matching.
    """
    import os
    normalized_req_path = os.path.abspath(requested_path)

    is_allowed = False
    for rule in file_permission_rules:
        rule_path_prefix = rule.get("path_prefix")
        if rule_path_prefix:
            normalized_rule_path = os.path.abspath(rule_path_prefix)
            # Ensure prefix ends with / unless it's the root '/'
            if not normalized_rule_path.endswith(os.sep) and normalized_rule_path != os.sep:
                normalized_rule_path += os.sep

            # Check if requested path starts with the rule prefix
            if normalized_req_path.startswith(normalized_rule_path) or normalized_req_path == os.path.abspath(rule_path_prefix):
                if required_permission in rule.get("permissions", []):
                    is_allowed = True
                    break # Found an allowing rule

    logger.debug(f"Permission check: path='{normalized_req_path}', required='{required_permission}', allowed={is_allowed}")
    return is_allowed
