import logging
import datetime
from typing import Optional, Dict # Added Dict
from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from ..registry import operation_registry # Import registry to list operations
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class Echo(Operation):
    name = "echo"
    description = "Returns the arguments it received. Useful for testing."
    arguments = [
        ArgumentDefinition(name="message", type="string", required=True, description="Message to echo back"),
        ArgumentDefinition(name="details", type="object", required=False, default={}, description="Optional additional details")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        # Use model_dump instead of dict for Pydantic V2+
        logger.debug(f"Executing echo with args: {args.model_dump()}, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")
        # No specific permissions needed for echo itself
        # Use model_dump instead of dict for Pydantic V2+
        return OperationResult(success=True, data=args.model_dump())

class ListOperations(Operation):
    name = "list_operations"
    description = "Lists available operations based on agent permissions."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        agent_id = agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'
        logger.debug(f"Executing list_operations for agent='{agent_id}'")
        all_ops = operation_registry.get_all()
        op_list = []

        allowed_ops_filter = agent_permissions.get('allowed_operations', []) if agent_permissions else []
        show_all = "*" in allowed_ops_filter

        for name, op_instance in sorted(all_ops.items()): # Sort for consistent output
            if show_all or name in allowed_ops_filter:
                # Convert ArgumentDefinition dataclasses to dictionaries for JSON serialization
                arguments_dict = []
                for arg_def in op_instance.arguments:
                    arg_data = {
                        "name": arg_def.name,
                        "type": arg_def.type,
                        "required": arg_def.required,
                        "description": arg_def.description,
                    }
                    # Only include default if it's not None (or handle other non-serializable defaults)
                    if arg_def.default is not None:
                        arg_data["default"] = arg_def.default
                    arguments_dict.append(arg_data)

                op_list.append({
                    "name": name,
                    "description": op_instance.description,
                    "arguments": arguments_dict
                })

        return OperationResult(success=True, data={"operations": op_list})

class Ping(Operation):
    name = "ping"
    description = "A simple health check operation that returns 'pong'."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug(f"Executing ping, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")
        # No specific permissions needed
        return OperationResult(success=True, data={"reply": "pong"})

class GetServerTime(Operation):
    name = "get_server_time"
    description = "Returns the current UTC date and time on the server."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug(f"Executing get_server_time, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")
        # No specific permissions needed
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        # Use isoformat() directly. It handles UTC representation correctly (usually with +00:00 or Z).
        time_str = now_utc.isoformat(timespec='milliseconds')
        # Ensure 'Z' is used for UTC if isoformat doesn't add it or +00:00
        if '+00:00' not in time_str and not time_str.endswith('Z'):
             time_str += 'Z'
        elif '+00:00' in time_str: # Replace +00:00 with Z for consistency if desired, though both are valid ISO 8601
             time_str = time_str.replace('+00:00', 'Z')

        return OperationResult(success=True, data={"utc_time": time_str})
