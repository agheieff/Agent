import logging
from .base import Capability, CapabilityResult, ArgumentDefinition
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

# --- ListCapabilities ---
class ListCapabilities(Capability):
    name = "list_capabilities"
    description = "Lists all available capabilities registered with the server."
    arguments = [] # No arguments needed

    def execute(self, args: BaseModel) -> CapabilityResult:
        logger.debug("Executing list_capabilities")
        all_caps = capability_registry.get_all()
        cap_list = []
        for name, cap_instance in all_caps.items():
            cap_list.append({
                "name": name,
                "description": cap_instance.description,
                "arguments": [vars(arg_def) for arg_def in cap_instance.arguments] # Convert dataclass to dict
            })

        return CapabilityResult(success=True, data={"capabilities": cap_list})
