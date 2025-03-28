import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import copy

logger = logging.getLogger(__name__)

# Define a simpler permissions configuration
DEFAULT_PERMISSIONS_CONFIG = {
    "agents": {
        "agent-001": {
            # This agent can read/write/list/delete in /tmp/agent_data/
            # and use default + file ops + finish_goal
            "groups": ["default_user", "tmp_readers_writers"]
        },
        "agent-admin": {
            # This agent can do anything, including execute_command
            "groups": ["admin"]
        },
        "readonly-agent": {
            # This agent can only read/list docs and use default ops
            "groups": ["default_user", "doc_readers"]
        },
        # Add the agent ID used in run.py by default
        "autonomous-agent-007": {
             "groups": ["default_user", "tmp_readers_writers"]
        }
    },
    "groups": {
        "default_user": {
            "allowed_operations": [
                "echo", "ping", "get_server_time", "list_operations"
                # Note: finish_goal is NOT included by default
            ],
            "file_permissions": []
        },
        "tmp_readers_writers": {
            "allowed_operations": [
                "read_file", "write_file", "delete_file", "list_directory",
                "finish_goal" # Allow agents in this group to finish goals
            ],
            "file_permissions": [
                # This path prefix will be dynamically patched by the conftest.py fixture during tests
                # For live runs, ensure this directory exists and is appropriate
                {"path_prefix": "/tmp/agent_data/", "permissions": ["read", "write", "delete", "list"]}
            ]
        },
        "doc_readers": {
            "allowed_operations": ["read_file", "list_directory"],
            "file_permissions": [
                {"path_prefix": "/shared/docs/", "permissions": ["read", "list"]}
            ]
        },
        "admin": {
            "allowed_operations": ["*"], # Wildcard allows ALL registered operations
            "file_permissions": [
                # Admin has full file access (use with caution)
                {"path_prefix": "/", "permissions": ["read", "write", "delete", "list"]}
            ]
            # Since '*' is used for allowed_operations, admin implicitly gets:
            # execute_command, finish_goal, and all others.
        },
        # Example of a more restricted command execution group (if needed later)
        # "safe_command_executor": {
        #     "allowed_operations": ["execute_command"],
        #     "command_whitelist": ["ls", "pwd", "/usr/bin/safe_script.sh"], # Hypothetical whitelist
        #     "file_permissions": [...]
        # }
    },
    "default_permissions": {
        # Permissions for unidentified agents or those not in the 'agents' map
        "allowed_operations": ["echo", "ping", "list_operations"],
        "file_permissions": []
    }
}

# Config that can be patched by tests or loaded dynamically later
# We need to ensure this variable name matches what's used in the module (e.g., conftest.py)
PERMISSIONS_CONFIG = copy.deepcopy(DEFAULT_PERMISSIONS_CONFIG)

def get_agent_permissions(agent_id: Optional[str]) -> Dict[str, Any]:
    """Get effective permissions for an agent by merging group permissions."""
    config_to_use = PERMISSIONS_CONFIG # Use the potentially patched config

    effective_permissions = copy.deepcopy(config_to_use.get("default_permissions", {}))
    effective_permissions["agent_id"] = agent_id or "default" # Track the agent ID

    if agent_id and agent_id in config_to_use.get("agents", {}):
        agent_groups = config_to_use["agents"][agent_id].get("groups", [])
        logger.debug(f"Agent '{agent_id}' found with groups: {agent_groups}")

        # Combine permissions from all assigned groups
        allowed_ops_set = set(effective_permissions.get("allowed_operations", []))
        file_perms_list = list(effective_permissions.get("file_permissions", []))
        # Store other custom permissions (like command_whitelist)
        custom_perms = {}

        has_wildcard_ops = "*" in allowed_ops_set

        for group_name in agent_groups:
            group_config = config_to_use.get("groups", {}).get(group_name)
            if group_config:
                logger.debug(f"Applying permissions from group '{group_name}'")
                group_ops = group_config.get("allowed_operations", [])
                if "*" in group_ops:
                    has_wildcard_ops = True
                if not has_wildcard_ops: # Only add specific ops if no wildcard encountered yet
                     allowed_ops_set.update(group_ops)

                # Simple merge for file perms (duplicates are okay, handled by check logic)
                file_perms_list.extend(group_config.get("file_permissions", []))

                # Merge other custom keys (simple overwrite, last group wins for conflicts)
                for key, value in group_config.items():
                    if key not in ["allowed_operations", "file_permissions"]:
                        custom_perms[key] = value
            else:
                logger.warning(f"Agent '{agent_id}' assigned to non-existent group '{group_name}'")

        # Finalize combined permissions
        if has_wildcard_ops:
             effective_permissions["allowed_operations"] = ["*"]
        else:
             # Sort for consistency
             effective_permissions["allowed_operations"] = sorted(list(allowed_ops_set))

        effective_permissions["file_permissions"] = file_perms_list
        effective_permissions.update(custom_perms) # Add any other merged keys

    else:
         logger.debug(f"Agent '{agent_id}' not found or is None. Using default permissions.")


    logger.debug(f"Effective permissions for agent '{effective_permissions['agent_id']}': {effective_permissions}")
    return effective_permissions


def check_file_permission(path_str: str, permission: str, rules: List[Dict]) -> bool:
    """
    Check if a resolved path has a specific permission based on hierarchical rules.
    The rule with the longest matching path_prefix applies.
    """
    if not path_str or not rules:
        return False

    try:
        # Resolve the target path (without requiring it to exist yet for write/delete)
        target_path = Path(path_str).resolve(strict=False)
    except Exception as e:
        logger.warning(f"Could not resolve target path '{path_str}' for permission check: {e}")
        return False # Cannot check permissions on an invalid path format

    best_match_rule = None
    longest_prefix_len = -1

    for rule in rules:
        rule_prefix_str = rule.get("path_prefix")
        if not rule_prefix_str:
            continue

        try:
            # Resolve the rule's prefix path
            rule_prefix_path = Path(rule_prefix_str).resolve(strict=False)
            current_prefix_len = len(str(rule_prefix_path))

            # Check if the target path is *equal to* or *inside* the rule prefix path
            is_match = (target_path == rule_prefix_path or rule_prefix_path in target_path.parents)

            if is_match and current_prefix_len > longest_prefix_len:
                longest_prefix_len = current_prefix_len
                best_match_rule = rule

        except Exception as e:
            logger.warning(f"Could not resolve rule prefix path '{rule_prefix_str}' for permission check: {e}")
            continue # Skip invalid rule paths

    # Check if the best matching rule grants the required permission
    if best_match_rule:
        allowed_perms = best_match_rule.get("permissions", [])
        if permission in allowed_perms:
            logger.debug(f"Permission '{permission}' granted for '{target_path}' by rule: {best_match_rule}")
            return True
        else:
             logger.debug(f"Permission '{permission}' denied for '{target_path}'. Best matching rule {best_match_rule} does not grant it.")
             return False
    else:
         logger.debug(f"Permission '{permission}' denied for '{target_path}'. No matching rule found.")
         return False

# --- Placeholder for command execution checks (if needed later) ---
# def check_command_permission(command: str, agent_permissions: Dict) -> bool:
#     """Checks if a command is allowed based on agent permissions (e.g., whitelist/blacklist)."""
#     command_whitelist = agent_permissions.get("command_whitelist")
#     command_blacklist = agent_permissions.get("command_blacklist")
#
#     # Example: Allow if whitelisted or if no whitelist exists and not blacklisted
#     base_command = shlex.split(command)[0] # Get the executable part
#
#     if command_whitelist is not None: # If whitelist exists, command MUST be in it
#         return base_command in command_whitelist
#     elif command_blacklist is not None: # If no whitelist, check blacklist
#         return base_command not in command_blacklist
#     else: # No whitelist or blacklist defined, allow (depends on desired default behavior)
#         return True
