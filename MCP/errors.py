# --- File: MCP/errors.py ---

from enum import IntEnum
from typing import Optional, Any

class ErrorCode(IntEnum):
    """Standardized error codes for MCP operations."""
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INVALID_REQUEST = 2
    OPERATION_NOT_FOUND = 10
    INVALID_ARGUMENTS = 11
    VALIDATION_ERROR = 12
    PERMISSION_DENIED = 13
    OPERATION_FAILED = 100
    OS_PERMISSION_DENIED = 101
    RESOURCE_NOT_FOUND = 102
    RESOURCE_EXISTS = 103
    RESOURCE_BUSY = 104
    NETWORK_ERROR = 105
    TIMEOUT = 106
    INVALID_OPERATION_STATE = 107

# Simple mapping for default error messages
DEFAULT_MESSAGES = {code: code.name.replace('_', ' ').capitalize() for code in ErrorCode}

class MCPError(Exception):
    """Custom exception for controlled errors within MCP operations."""
    def __init__(self, code: ErrorCode, message: Optional[str] = None, details: Optional[Any] = None):
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, str(code))
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        detail_str = f" Details: {self.details}" if self.details else ""
        return f"[MCPError Code={self.code.value} ({self.code.name})]: {self.message}{detail_str}"