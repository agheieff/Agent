import logging
import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from ..registry import operation_registry # Import registry to list operations

logger = logging.getLogger(__name__)

class Echo(Operation):
    name = "echo"
    description = "Returns the exact arguments it received. Useful for testing."
    arguments = [
        ArgumentDefinition(name="message", type="string", required=True, description="Message to echo back"),
        ArgumentDefinition(name="details", type="object", required=False, default={}, description="Optional additional details as a JSON object")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        # args is already a validated Pydantic model instance
        logger.debug(f"Executing echo with args: {args.model_dump()}")
        # No specific permissions needed for echo itself
        return OperationResult(success=True, data=args.model_dump())


class ListOperations(Operation):
    name = "list_operations"
    description = "Lists available operations based on the calling agent's permissions."
    arguments = [] # No arguments needed

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        agent_id = agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'
        logger.debug(f"Executing list_operations for agent='{agent_id}'")

        all_ops_instances = operation_registry.get_all()
        allowed_op_names = agent_permissions.get('allowed_operations', []) if agent_permissions else []
        show_all = "*" in allowed_op_names

        op_list = []
        for op_name, op_instance in sorted(all_ops_instances.items()):
            if show_all or op_name in allowed_op_names:
                 # Convert ArgumentDefinition dataclasses to dictionaries
                arguments_dict = [
                    {
                         "name": arg_def.name,
                         "type": arg_def.type,
                         "required": arg_def.required,
                         "description": arg_def.description,
                         # Only include default if it's defined (not None)
                         **({"default": arg_def.default} if arg_def.default is not None else {})
                     }
                    for arg_def in op_instance.arguments
                ]

                op_list.append({
                    "name": op_name,
                    "description": op_instance.description,
                    "arguments": arguments_dict
                })

        return OperationResult(success=True, data={"operations": op_list})


class Ping(Operation):
    name = "ping"
    description = "A simple health check operation that returns 'pong'."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug(f"Executing ping")
        return OperationResult(success=True, data={"reply": "pong"})


class GetServerTime(Operation):
    name = "get_server_time"
    description = "Returns the current UTC date and time on the server in ISO 8601 format."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug(f"Executing get_server_time")
        # Ensure timezone-aware datetime object in UTC
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        # isoformat() correctly handles UTC representation (with Z or +00:00)
        time_str = now_utc.isoformat(timespec='milliseconds')

        # Optional: Force 'Z' suffix if preferred over '+00:00'
        if time_str.endswith('+00:00'):
            time_str = time_str[:-6] + 'Z'

        return OperationResult(success=True, data={"utc_time": time_str})
