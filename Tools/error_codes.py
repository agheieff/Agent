class ErrorCodes:
    # Success (0)
    SUCCESS = 0
    
    # Special (-1)
    TOOL_NOT_FOUND = -1
    
    # Standard errors (1-9)
    GENERAL_ERROR = 1
    INVALID_OPERATION = 2
    OPERATION_FAILED = 3
    
    # Input/Argument errors (10-29)
    INVALID_ARGUMENTS = 10
    MISSING_REQUIRED_ARGUMENT = 11
    INVALID_ARGUMENT_TYPE = 12
    INVALID_ARGUMENT_VALUE = 13
    
    # Permission/Access errors (30-49)
    PERMISSION_DENIED = 30
    AUTHENTICATION_FAILED = 31
    ACCESS_DENIED = 32
    
    # Resource errors (50-69)
    RESOURCE_NOT_FOUND = 50
    RESOURCE_EXISTS = 51
    RESOURCE_UNAVAILABLE = 52
    RESOURCE_BUSY = 53
    
    # Network/Connection errors (70-89)
    NETWORK_ERROR = 70
    CONNECTION_FAILED = 71
    TIMEOUT = 72
    
    # Internal/Unknown errors (90-99)
    INTERNAL_ERROR = 90
    UNKNOWN_ERROR = 99

# Default messages for each error code
DEFAULT_MESSAGES = {
    ErrorCodes.SUCCESS: "Operation completed successfully",
    ErrorCodes.TOOL_NOT_FOUND: "Tool does not exist",
    
    ErrorCodes.GENERAL_ERROR: "A general error occurred",
    ErrorCodes.INVALID_OPERATION: "Invalid operation",
    ErrorCodes.OPERATION_FAILED: "Operation failed",
    
    ErrorCodes.INVALID_ARGUMENTS: "Invalid arguments provided",
    ErrorCodes.MISSING_REQUIRED_ARGUMENT: "Missing required argument",
    ErrorCodes.INVALID_ARGUMENT_TYPE: "Invalid argument type",
    ErrorCodes.INVALID_ARGUMENT_VALUE: "Invalid argument value",
    
    ErrorCodes.PERMISSION_DENIED: "Permission denied",
    ErrorCodes.AUTHENTICATION_FAILED: "Authentication failed",
    ErrorCodes.ACCESS_DENIED: "Access denied",
    
    ErrorCodes.RESOURCE_NOT_FOUND: "Resource not found",
    ErrorCodes.RESOURCE_EXISTS: "Resource already exists",
    ErrorCodes.RESOURCE_UNAVAILABLE: "Resource is unavailable",
    ErrorCodes.RESOURCE_BUSY: "Resource is busy",
    
    ErrorCodes.NETWORK_ERROR: "Network error occurred",
    ErrorCodes.CONNECTION_FAILED: "Connection failed",
    ErrorCodes.TIMEOUT: "Operation timed out",
    
    ErrorCodes.INTERNAL_ERROR: "Internal error occurred",
    ErrorCodes.UNKNOWN_ERROR: "Unknown error occurred"
} 