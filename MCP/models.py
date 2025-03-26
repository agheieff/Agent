from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal, Union

# Using Literal for fixed 'type' and 'status' fields improves validation
class MCPRequest(BaseModel):
    mcp_version: str = Field(default="1.0", description="MCP Protocol Version", examples=["1.0"])
    type: Literal["request"] = "request"
    id: str = Field(..., description="Unique request identifier", examples=["req-abc-123"])
    capability: str = Field(..., description="The name of the capability to execute", examples=["read_file"])
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the capability", examples=[{"path": "/etc/hosts"}])

class MCPResponseBase(BaseModel):
    mcp_version: str = Field(default="1.0", description="MCP Protocol Version")
    type: Literal["response"] = "response"
    id: str = Field(..., description="Corresponds to the request ID")

class MCPSuccessResponse(MCPResponseBase):
    status: Literal["success"] = "success"
    result: Optional[Any] = Field(None, description="The successful result data from the capability")

class MCPErrorResponse(MCPResponseBase):
    status: Literal["error"] = "error"
    error_code: int = Field(..., description="Numeric error code")
    message: str = Field(..., description="Human-readable error message")

# Union type for response model in FastAPI documentation (optional)
MCPResponse = Union[MCPSuccessResponse, MCPErrorResponse]
