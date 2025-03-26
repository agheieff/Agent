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
        logger.debug(f"Executing echo with args: {args.dict()}, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")
        # No specific permissions needed for echo itself
        return OperationResult(success=True, data=args.dict())

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
        time_str = now_utc.isoformat(timespec='milliseconds') + 'Z' # Common ISO format with Z for UTC
        return OperationResult(success=True, data={"utc_time": time_str})
