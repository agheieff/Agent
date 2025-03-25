import os
from Tools.base import Tool, Argument, ArgumentType, ToolConfig, ErrorCodes, ToolResult

class WriteFile(Tool):
    def __init__(self):
        config = ToolConfig()
        
        super().__init__(
            name="write_file",
            description="Writes content to a file",
            help_text="Writes text content to the specified file. Optionally overwrites if file exists.",
            arguments=[
                Argument("path", ArgumentType.FILEPATH, "File path"),
                Argument("content", ArgumentType.STRING, "Content to write"),
                Argument("overwrite", ArgumentType.BOOLEAN, "Overwrite if exists", is_optional=True, default_value=False)
            ],
            config=config
        )

    def _execute(self, path=None, content=None, overwrite=False):
        # Check if path is a directory
        if os.path.isdir(path):
            return ErrorCodes.RESOURCE_EXISTS, f"'{path}' is a directory, not a file."
        
        # Check if the directory portion exists
        directory = os.path.dirname(path) or '.'
        if not os.path.exists(directory):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"Directory '{directory}' does not exist."
        
        # Check write permission
        if not os.access(directory, os.W_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No write permission in directory '{directory}'."
        
        # If file exists and not overwriting
        if os.path.exists(path) and not overwrite:
            return ErrorCodes.RESOURCE_EXISTS, f"File '{path}' already exists. Use 'overwrite=True' to replace it."
        
        # Attempt to write
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return ErrorCodes.SUCCESS, None
        except PermissionError as e:
            return ErrorCodes.PERMISSION_DENIED, f"Permission denied: {str(e)}"
        except OSError as e:
            return ErrorCodes.OPERATION_FAILED, f"OS error: {str(e)}"
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Unexpected error: {str(e)}"
