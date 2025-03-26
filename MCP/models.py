from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal, Union

class MCPRequest(BaseModel):
    mcp_version: str = Field(default="1.0", ...)
    type: Literal["request"] = "request"
    id: str = Field(..., examples=["req-abc-123"])
    operation: str = Field(..., description="The name of the operation to execute", examples=["read_file"]) # RENAMED
    arguments: Dict[str, Any] = Field(default_factory=dict, ...)
    agent_id: Optional[str] = Field(None, description="Identifier for the agent making the request (optional)") # ADDED for Phase 2

class MCPResponseBase(BaseModel):
    mcp_version: str = Field(default="1.0", ...)
    type: Literal["response"] = "response"
    id: str = Field(...)

class MCPSuccessResponse(MCPResponseBase):
    status: Literal["success"] = "success"
    result: Optional[Any] = Field(None, ...)

class MCPErrorResponse(MCPResponseBase):
    status: Literal["error"] = "error"
    error_code: int = Field(...)
    message: str = Field(...)

MCPResponse = Union[MCPSuccessResponse, MCPErrorResponse]
