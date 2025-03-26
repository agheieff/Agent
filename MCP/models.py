from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal, Union

class MCPRequest(BaseModel):
    mcp_version: str = Field(default="1.0", description="MCP Protocol Version", examples=["1.0"])
    type: Literal["request"] = "request"
    id: str = Field(..., description="Unique request identifier", examples=["req-xyz-789"])
    operation: str = Field(..., description="The name of the operation to execute", examples=["read_file"])
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the operation", examples=[{"path": "/data/input.txt"}])
    agent_id: Optional[str] = Field(None, description="Identifier for the agent making the request (optional)", examples=["agent-007", None])

class MCPResponseBase(BaseModel):
    mcp_version: str = Field(default="1.0", description="MCP Protocol Version")
    type: Literal["response"] = "response"
    id: str = Field(..., description="Corresponds to the request ID")

class MCPSuccessResponse(MCPResponseBase):
    status: Literal["success"] = "success"
    result: Optional[Any] = Field(None, description="The successful result data from the operation")

class MCPErrorResponse(MCPResponseBase):
    status: Literal["error"] = "error"
    error_code: int = Field(..., description="Numeric error code (defined in MCP.errors.ErrorCode)")
    message: str = Field(..., description="Human-readable error message")

# Union type for response model hint in FastAPI documentation (optional but helpful)
MCPResponse = Union[MCPSuccessResponse, MCPErrorResponse]
