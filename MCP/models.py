from pydantic import BaseModel, Field, validator
from typing import Dict, Any, Optional, Literal, Union

# Use standard UUID for request IDs if desired, but keep string for flexibility
# import uuid

class MCPRequest(BaseModel):
    """Schema for incoming MCP requests."""
    mcp_version: str = Field(default="1.0", description="MCP Protocol Version", examples=["1.0"])
    type: Literal["request"] = Field(default="request", description="Message type")
    id: str = Field(..., description="Unique request identifier (UUID recommended)", examples=["req-123e4567-e89b-12d3-a456-426614174000"])
    operation: str = Field(..., description="The name of the operation to execute", examples=["read_file"])
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the operation", examples=[{"path": "/data/input.txt"}])
    agent_id: Optional[str] = Field(None, description="Identifier for the agent making the request (used for permissions)", examples=["agent-007", None])

    # Example validator
    # @validator('id')
    # def id_must_be_uuid_like(cls, v):
    #     # Simple check, not full UUID validation
    #     if not isinstance(v, str) or len(v) < 10:
    #          raise ValueError('id must be a reasonably unique string')
    #     return v


class MCPResponseBase(BaseModel):
    """Base schema for MCP responses."""
    mcp_version: str = Field(default="1.0", description="MCP Protocol Version")
    type: Literal["response"] = Field(default="response", description="Message type")
    id: str = Field(..., description="Corresponds to the request ID")


class MCPSuccessResponse(MCPResponseBase):
    """Schema for successful MCP responses."""
    status: Literal["success"] = "success"
    result: Optional[Any] = Field(None, description="The successful result data from the operation")


class MCPErrorResponse(MCPResponseBase):
    """Schema for error MCP responses."""
    status: Literal["error"] = "error"
    error_code: int = Field(..., description="Numeric error code (from MCP.errors.ErrorCode enum)", examples=[13, 102])
    message: str = Field(..., description="Human-readable error message", examples=["Permission denied", "File not found"])
    details: Optional[Any] = Field(None, description="Optional additional error details (e.g., validation errors)")


# Union type for documentation and type hinting
MCPResponse = Union[MCPSuccessResponse, MCPErrorResponse]
