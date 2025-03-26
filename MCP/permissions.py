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
            "groups": ["default_user", "tmp_readers_writers"]
        },
        "agent-admin": {
            "groups": ["admin"]
        },
        "readonly-agent": {
            "groups": ["default_user", "doc_readers"]
        }
    },
    "groups": {
        "default_user": {
            "allowed_operations": [
                "echo", "ping", "get_server_time", "list_operations"
            ],
            "file_permissions": []
        },
        "tmp_readers_writers": {
            "allowed_operations": [
                "read_file", "write_file", "delete_file", "list_directory"
            ],
            "file_permissions": [
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
            "allowed_operations": ["*"],
            "file_permissions": [
                {"path_prefix": "/", "permissions": ["read", "write", "delete", "list"]}
            ]
        },
    },
    "default_permissions": {
        "allowed_operations": ["echo", "ping", "list_operations"],
        "file_permissions": []
    }
}

# Config that can be patched by tests
PERMISSIONS_CONFIG = copy.deepcopy(DEFAULT_PERMISSIONS_CONFIG)

def get_agent_permissions(agent_id: Optional[str]) -> Dict[str, Any]:
    """Get effective permissions for an agent."""
    if not agent_id or agent_id not in PERMISSIONS_CONFIG.get("agents", {}):
        return PERMISSIONS_CONFIG.get("default_permissions", {}).copy()
    
    # Get groups for this agent
    agent_groups = PERMISSIONS_CONFIG.get("agents", {}).get(agent_id, {}).get("groups", [])
    
    # Combine permissions from all groups
    allowed_ops = set()
    file_perms = []
    
    for group in agent_groups:
        group_config = PERMISSIONS_CONFIG.get("groups", {}).get(group, {})
        allowed_ops.update(group_config.get("allowed_operations", []))
        file_perms.extend(group_config.get("file_permissions", []))
    
    # Handle wildcard for operations
    final_allowed_ops = ["*"] if "*" in allowed_ops else sorted(list(allowed_ops))
    
    return {
        "agent_id": agent_id,
        "allowed_operations": final_allowed_ops,
        "file_permissions": file_perms
    }

def check_file_permission(path: str, permission: str, rules: List[Dict]) -> bool:
    """Check if a path has a specific permission based on rules."""
    if not path:
        return False
    
    try:
        resolved_path = Path(path).resolve(strict=False)
    except Exception:
        return False
    
    # Find best matching rule (longest path prefix)
    best_match = None
    longest_prefix = -1
    
    for rule in rules:
        rule_path = rule.get("path_prefix", "")
        try:
            resolved_rule_path = Path(rule_path).resolve(strict=False)
            prefix_len = len(str(resolved_rule_path))
            
            # Check if requested path is within rule path
            is_match = (resolved_path == resolved_rule_path or 
                      resolved_rule_path in resolved_path.parents)
                      
            if is_match and prefix_len > longest_prefix:
                longest_prefix = prefix_len
                best_match = rule
        except Exception:
            continue
    
    # Check if permission is allowed by best match
    if best_match and permission in best_match.get("permissions", []):
        return True
    
    return False