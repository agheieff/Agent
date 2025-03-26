# --- File: MCP/errors.py ---

from enum import IntEnum
from typing import Optional, Any # <-- Import Any here

class ErrorCode(IntEnum):
    """Standardized error codes for MCP operations."""
    # General MCP/Server Errors (0-99)
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INVALID_REQUEST = 2         # Malformed MCP request structure
    OPERATION_NOT_FOUND = 10
    INVALID_ARGUMENTS = 11      # Correct types, but invalid values (e.g., path is dir not file)
    VALIDATION_ERROR = 12       # Failed Pydantic validation (wrong types, missing required)
    PERMISSION_DENIED = 13      # Agent lacks permission for operation or specific resource access

    # Operation Execution Errors (100-199)
    OPERATION_FAILED = 100      # Generic failure within operation logic
    OS_PERMISSION_DENIED = 101  # Specific OS-level permission issue encountered
    RESOURCE_NOT_FOUND = 102    # e.g., File not found
    RESOURCE_EXISTS = 103       # e.g., File exists and overwrite=False
    RESOURCE_BUSY = 104         # e.g., File locked
    NETWORK_ERROR = 105         # External network issue during operation (e.g., calling another service)
    TIMEOUT = 106               # Operation took too long
    INVALID_OPERATION_STATE = 107 # e.g., trying to write to read-only resource

    # Add more specific codes as needed

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
    ErrorCode.RESOURCE_EXISTS: "A resource conflict occurred (e.g., resource exists)",
    ErrorCode.RESOURCE_BUSY: "A required resource is busy or locked",
    ErrorCode.NETWORK_ERROR: "A network error occurred during the operation",
    ErrorCode.TIMEOUT: "The operation timed out",
    ErrorCode.INVALID_OPERATION_STATE: "The operation cannot be performed in the current state",
}

class MCPError(Exception):
    """Custom exception for controlled errors within MCP operations."""
    def __init__(self, code: ErrorCode, message: Optional[str] = None, details: Optional[Any] = None):
        self.code = code
        # Use provided message, lookup default, or fallback to generic error name
        self.message = message or DEFAULT_MESSAGES.get(code, code.name)
        self.details = details # Optional field for more context
        super().__init__(self.message)

    def __str__(self):
         detail_str = f" Details: {self.details}" if self.details else ""
         return f"[MCPError Code={self.code.value} ({self.code.name})]: {self.message}{detail_str}"
