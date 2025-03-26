from enum import IntEnum

class ErrorCode(IntEnum):
    SUCCESS = 0
    UNKNOWN_ERROR = 1
    INVALID_REQUEST = 2
    CAPABILITY_NOT_FOUND = 10
    INVALID_ARGUMENTS = 11
    VALIDATION_ERROR = 12

    OPERATION_FAILED = 100
    PERMISSION_DENIED = 101
    RESOURCE_NOT_FOUND = 102
    RESOURCE_EXISTS = 103
    RESOURCE_BUSY = 104
    NETWORK_ERROR = 105
    TIMEOUT = 106

DEFAULT_MESSAGES = {
    ErrorCode.SUCCESS: "Operation successful",
    ErrorCode.UNKNOWN_ERROR: "An unknown internal error occurred",
    ErrorCode.INVALID_REQUEST: "The received request was malformed or invalid",
    ErrorCode.CAPABILITY_NOT_FOUND: "The requested capability was not found",
    ErrorCode.INVALID_ARGUMENTS: "Invalid arguments provided for the capability",
    ErrorCode.VALIDATION_ERROR: "Argument validation failed",
    ErrorCode.OPERATION_FAILED: "The capability execution failed",
    ErrorCode.PERMISSION_DENIED: "Permission denied during capability execution",
    ErrorCode.RESOURCE_NOT_FOUND: "A required resource was not found",
    ErrorCode.RESOURCE_EXISTS: "A resource that should not exist already exists",
}

class MCPError(Exception):
    """Custom exception for controlled errors within capabilities."""
    def __init__(self, code: ErrorCode, message: Optional[str] = None):
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "An error occurred")
        super().__init__(self.message)
