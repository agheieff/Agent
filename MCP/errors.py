from enum import IntEnum
from typing import Optional

class ErrorCode(IntEnum):
    # General MCP/Server Errors (0-99)
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INVALID_REQUEST = 2
    OPERATION_NOT_FOUND = 10
    INVALID_ARGUMENTS = 11
    VALIDATION_ERROR = 12
    PERMISSION_DENIED = 13 # General permission denied (e.g., operation level)

    # Operation Execution Errors (100+)
    OPERATION_FAILED = 100
    # Specific permission errors during execution (e.g., file access) can also use 101
    # Or potentially define more granular codes like FILE_READ_DENIED = 110 etc.
    OS_PERMISSION_DENIED = 101 # More specific for OS level issues if needed
    RESOURCE_NOT_FOUND = 102
    RESOURCE_EXISTS = 103
    RESOURCE_BUSY = 104
    NETWORK_ERROR = 105
    TIMEOUT = 106
    INVALID_OPERATION_STATE = 107 # e.g., trying to write to read-only file


DEFAULT_MESSAGES = {
    ErrorCode.SUCCESS: "Operation successful",
    ErrorCode.UNKNOWN_ERROR: "An unknown internal error occurred",
    ErrorCode.INVALID_REQUEST: "The received request was malformed or invalid",
    ErrorCode.OPERATION_NOT_FOUND: "The requested operation was not found",
    ErrorCode.INVALID_ARGUMENTS: "Invalid arguments provided for the operation",
    ErrorCode.VALIDATION_ERROR: "Argument validation failed",
    ErrorCode.PERMISSION_DENIED: "Permission denied",
    ErrorCode.OPERATION_FAILED: "The operation execution failed",
    ErrorCode.OS_PERMISSION_DENIED: "Operating system permission denied during operation",
    ErrorCode.RESOURCE_NOT_FOUND: "A required resource was not found",
    ErrorCode.RESOURCE_EXISTS: "A resource conflict occurred (e.g., file exists)",
    ErrorCode.RESOURCE_BUSY: "A required resource is busy or locked",
    ErrorCode.NETWORK_ERROR: "A network error occurred during the operation",
    ErrorCode.TIMEOUT: "The operation timed out",
    ErrorCode.INVALID_OPERATION_STATE: "The operation cannot be performed in the current state",
}

class MCPError(Exception):
    """Custom exception for controlled errors within operations."""
    def __init__(self, code: ErrorCode, message: Optional[str] = None):
        self.code = code
        # Use provided message or lookup default, fallback to generic error
        self.message = message or DEFAULT_MESSAGES.get(code, "An unspecified error occurred")
        super().__init__(self.message)
