from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal, Union

class MCPRequest(BaseModel):
    """Schema for incoming MCP requests."""
    mcp_version: str = "1.0"
    type: Literal["request"] = "request"
    id: str
    operation: str
    arguments: Dict[str, Any] = {}
    agent_id: Optional[str] = None

class MCPResponseBase(BaseModel):
    """Base schema for MCP responses."""
    mcp_version: str = "1.0"
    type: Literal["response"] = "response"
    id: str

class MCPSuccessResponse(MCPResponseBase):
    """Schema for successful MCP responses."""
    status: Literal["success"] = "success"
    result: Optional[Any] = None

class MCPErrorResponse(MCPResponseBase):
    """Schema for error MCP responses."""
    status: Literal["error"] = "error"
    error_code: int
    message: str
    details: Optional[Any] = None

# Union type for documentation and type hinting
MCPResponse = Union[MCPSuccessResponse, MCPErrorResponse]