import logging
import os
from pathlib import Path # Import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# --- Configuration ---
# Define permissions here directly as a Python dictionary for simplicity.
# In a real application, load this from a file (YAML, JSON, TOML).

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
            "file_permissions": []
        },
        "tmp_readers_writers": {
            "allowed_operations": [ # Explicitly list allowed file ops for this group
                "read_file",
                "write_file",
                "delete_file",
                "list_directory"
            ],
            "file_permissions": [
                # Grant R/W/D/L access within /tmp/agent_data/ (or OS equivalent)
                # **IMPORTANT**: Path normalization is CRUCIAL for security.
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
            "allowed_operations": ["*"], # Wildcard for all operations
            "file_permissions": [
                {"path_prefix": "/", "permissions": ["read", "write", "delete", "list"]} # Full access (use with extreme caution!)
            ]
        },
    },
    "default_permissions": { # Applied if agent_id is None or not found
        "allowed_operations": ["echo", "ping", "list_operations"], # Very limited default
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
    group permissions. Assumes no direct agent-specific permissions for now.
    """
    if not agent_id or agent_id not in PERMISSIONS_CONFIG["agents"]:
        logger.debug(f"Agent ID '{agent_id}' not found or not provided, using default permissions.")
        # Return a copy to prevent modification of the original default config
        return PERMISSIONS_CONFIG["default_permissions"].copy()

    # agent_conf = PERMISSIONS_CONFIG["agents"][agent_id] # Not used directly for merging yet
    agent_groups = _resolve_groups(agent_id)

    # Combine allowed operations from all groups
    effective_allowed_ops: Set[str] = set()
    for group_name in agent_groups:
        group_conf = PERMISSIONS_CONFIG["groups"].get(group_name, {})
        effective_allowed_ops.update(group_conf.get("allowed_operations", []))

    # Combine file permissions (simple list concatenation for now)
    effective_file_perms: List[Dict] = []
    for group_name in agent_groups:
        group_conf = PERMISSIONS_CONFIG["groups"].get(group_name, {})
        effective_file_perms.extend(group_conf.get("file_permissions", []))

    # Handle wildcard '*' in operations - if present, it overrides specific ops
    final_allowed_ops = ["*"] if "*" in effective_allowed_ops else sorted(list(effective_allowed_ops))

    effective_permissions = {
        "agent_id": agent_id,
        "groups": sorted(list(agent_groups)),
        "allowed_operations": final_allowed_ops,
        "file_permissions": effective_file_perms # Keep potentially overlapping rules for check_file_permission
    }
    logger.debug(f"Effective permissions for agent '{agent_id}': {effective_permissions}")
    return effective_permissions


def check_file_permission(
    requested_path_str: str,
    required_permission: str, # e.g., "read", "write", "delete", "list"
    file_permission_rules: List[Dict]
) -> bool:
    """
    Checks if the required permission is granted for the requested path
    based on the agent's file permission rules (list of dictionaries).

    Revised Implementation: Uses pathlib.Path.resolve() for robust normalization
    and finds the most specific matching prefix rule.
    """
    if not requested_path_str: # Prevent issues with empty path
        logger.debug("Permission check: Denied due to empty requested path.")
        return False

    try:
        # Resolve the requested path to get a canonical absolute path
        # This handles '..', symlinks, etc.
        resolved_req_path = Path(requested_path_str).resolve()
    except Exception as e:
        logger.warning(f"Could not resolve requested path '{requested_path_str}': {e}")
        return False # Treat un-resolvable paths as denied

    best_match_rule = None
    longest_prefix_len = -1

    for rule in file_permission_rules:
        rule_path_prefix_str = rule.get("path_prefix")
        if not rule_path_prefix_str:
            continue

        try:
            # Resolve the rule prefix path as well for consistent comparison
            resolved_rule_path = Path(rule_path_prefix_str).resolve()
            current_prefix_len = len(str(resolved_rule_path))

            # Check if the resolved requested path IS or IS WITHIN the resolved rule path
            # This works for both file and directory rules naturally with pathlib
            # resolved_req_path == resolved_rule_path handles exact matches (file or dir)
            # resolved_rule_path in resolved_req_path.parents handles containment
            # e.g., rule /a/b/, req /a/b/c -> Path('/a/b') in Path('/a/b/c').parents -> True
            # e.g., rule /a/b, req /a/b -> Path('/a/b') == Path('/a/b') -> True
            # e.g., rule /a/b/, req /a/b -> Path('/a/b') == Path('/a/b') -> True (resolve handles trailing slash)
            if resolved_req_path == resolved_rule_path or resolved_rule_path in resolved_req_path.parents:
                # Find the most specific rule (longest prefix path string) that applies
                if current_prefix_len > longest_prefix_len:
                    longest_prefix_len = current_prefix_len
                    best_match_rule = rule
                # If lengths are equal, current logic takes the last one found.
                # Could implement deny > allow precedence here if needed later.

        except Exception as e:
            logger.warning(f"Could not resolve rule path '{rule_path_prefix_str}': {e}")
            continue # Skip invalid rules

    # Now check the permissions of the best matching rule found
    is_allowed = False
    if best_match_rule:
        allowed_perms_for_rule = best_match_rule.get("permissions", [])
        if required_permission in allowed_perms_for_rule:
            is_allowed = True

    # Add more detailed logging
    logger.debug(
        f"Permission check: req_path='{resolved_req_path}' (orig='{requested_path_str}'), "
        f"required='{required_permission}', "
        f"best_match_rule={best_match_rule} (matched prefix='{str(Path(best_match_rule['path_prefix']).resolve()) if best_match_rule else 'None'}'), "
        f"allowed={is_allowed}"
    )
    return is_allowed
