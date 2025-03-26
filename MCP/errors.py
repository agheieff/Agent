from enum import IntEnum
from typing import Optional # Add this

class ErrorCode(IntEnum):
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INVALID_REQUEST = 2
    OPERATION_NOT_FOUND = 10 # RENAMED
    INVALID_ARGUMENTS = 11
    VALIDATION_ERROR = 12
    PERMISSION_DENIED = 101 # Moved here from capability errors
    OPERATION_FAILED = 100
    # PERMISSION_DENIED = 101 # Now defined above
    RESOURCE_NOT_FOUND = 102
    RESOURCE_EXISTS = 103
    RESOURCE_BUSY = 104
    NETWORK_ERROR = 105
    TIMEOUT = 106

DEFAULT_MESSAGES = {
    ErrorCode.SUCCESS: "Operation successful",
    ErrorCode.UNKNOWN_ERROR: "An unknown internal error occurred",
    ErrorCode.INVALID_REQUEST: "The received request was malformed or invalid",
    ErrorCode.OPERATION_NOT_FOUND: "The requested operation was not found", # UPDATED
    ErrorCode.INVALID_ARGUMENTS: "Invalid arguments provided for the operation",
    ErrorCode.VALIDATION_ERROR: "Argument validation failed",
    ErrorCode.OPERATION_FAILED: "The operation execution failed",
    ErrorCode.PERMISSION_DENIED: "Permission denied", # General permission denied
    ErrorCode.RESOURCE_NOT_FOUND: "A required resource was not found",
    ErrorCode.RESOURCE_EXISTS: "A resource that should not exist already exists",
    # ... add others
}

class MCPError(Exception):
    """Custom exception for controlled errors within operations."""
    def __init__(self, code: ErrorCode, message: Optional[str] = None):
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "An error occurred")
        super().__init__(self.message)
