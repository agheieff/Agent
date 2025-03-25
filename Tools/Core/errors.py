from enum import Enum

class ToolError(Enum):
    FILE_NOT_FOUND = "File not found"
    PERMISSION_DENIED = "Permission denied"
    INVALID_INPUT = "Invalid input parameters"
    
    def result(self, details: str = "") -> ToolResult:
        return ToolResult(
            success=False,
            output=details,
            error=self.value
        )
