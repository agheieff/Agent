import logging
import datetime
from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from ..registry import capability_registry # Import registry to list capabilities
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# --- Echo (Simple Test Capability) ---
class Echo(Capability):
    name = "echo"
    description = "Returns the arguments it received."
    arguments = [
        ArgumentDefinition(name="message", type="string", required=True, description="Message to echo back"),
        ArgumentDefinition(name="details", type="object", required=False, default={}, description="Optional additional details")
    ]

    def execute(self, args: BaseModel) -> CapabilityResult:
        logger.debug(f"Executing echo with args: {args.dict()}")
        return CapabilityResult(success=True, data=args.dict())

class ListOperations(Operation): # RENAMED
    name = "list_operations" # RENAMED
    description = "Lists all available operations registered with the server." # RENAMED
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug("Executing list_operations")
        all_ops = operation_registry.get_all() # RENAMED
        op_list = []
        # Optionally filter based on agent's allowed_operations permission
        allowed_ops_filter = agent_permissions.get('allowed_operations', []) if agent_permissions else []
        show_all = "*" in allowed_ops_filter

        for name, op_instance in all_ops.items():
             if show_all or name in allowed_ops_filter: # Apply filter
                 op_list.append({
                    "name": name,
                    "description": op_instance.description,
                    "arguments": [vars(arg_def) for arg_def in op_instance.arguments]
                 })

        return OperationResult(success=True, data={"operations": op_list}) # RENAMED field

# --- Ping ---
class Ping(Operation):
    name = "ping"
    description = "A simple health check operation that returns 'pong'."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug("Executing ping")
        return OperationResult(success=True, data={"reply": "pong"})

# --- GetServerTime ---
class GetServerTime(Operation):
    name = "get_server_time"
    description = "Returns the current UTC date and time on the server."
    arguments = []

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        logger.debug("Executing get_server_time")
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        # ISO 8601 format is standard and recommended
        time_str = now_utc.isoformat()
        return OperationResult(success=True, data={"utc_time": time_str})


