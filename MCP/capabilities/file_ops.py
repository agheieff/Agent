import os
from .base import Capability, CapabilityResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from pydantic import BaseModel # For type hinting the args parameter in execute

class ReadFileArgs(BaseModel): # Example explicit model if needed, or rely on dynamic one
    path: str
    lines: Optional[int] = None

class ReadFile(Capability):
    name = "read_file"
    description = "Reads content from a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file"),
        ArgumentDefinition(name="lines", type="integer", required=False, description="Number of lines to read (optional)")
    ]

    def execute(self, args: BaseModel) -> CapabilityResult: # Use BaseModel for validated args
        path = args.path # Access validated args directly
        lines_to_read = args.lines

        if not os.path.exists(path):
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File not found: {path}")
        if not os.path.isfile(path):
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a file: {path}")
        if not os.access(path, os.R_OK):
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"No read permission for file: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                if lines_to_read is not None and lines_to_read > 0:
                    content_lines = [next(f).rstrip('\n') for _ in range(lines_to_read)]
                    content = "\n".join(content_lines)
                else:
                    content = f.read()
            return CapabilityResult(success=True, data={"content": content})
        except StopIteration: # Handle reading fewer lines than requested if EOF is reached
             return CapabilityResult(success=True, data={"content": "\n".join(content_lines)})
        except Exception as e:
            # Catch specific file-related errors if possible
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to read file '{path}': {str(e)}") from e

# --- Add WriteFile, DeleteFile, ListDirectory capabilities similarly ---
# Remember to use 'raise MCPError(...)' for controlled failures.
