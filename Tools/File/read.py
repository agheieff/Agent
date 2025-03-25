from Tools.base import Tool, Argument, ArgumentType, ToolConfig, ErrorCodes

class ReadFile(Tool):
    def __init__(self):
        config = ToolConfig()
        
        super().__init__(
            name="read_file",
            description="Reads file contents",
            help_text="Reads lines from a text file. Tracks last file read for editing.",
            arguments=[
                Argument("path", ArgumentType.FILEPATH, "File path"),
                Argument("lines", ArgumentType.INT, "Lines to read", is_optional=True, default_value=100)
            ],
            config=config
        )
        self.last_read_file = None

    def _execute(self, path, lines=100):
        import os
        
        # Validate existence
        if not os.path.exists(path):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"File '{path}' does not exist."
        
        # Validate that it's a file (not directory)
        if not os.path.isfile(path):
            return ErrorCodes.INVALID_ARGUMENT_VALUE, f"Path '{path}' is not a file."
        
        # Validate read permission
        if not os.access(path, os.R_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No read permission for '{path}'."
        
        # Validate lines is int
        if not isinstance(lines, int):
            return ErrorCodes.INVALID_ARGUMENT_VALUE, f"Lines must be an integer, got {lines}."
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content_lines = f.readlines()
            # Update last_read_file
            self.last_read_file = path
            
            content = "".join(content_lines[:lines])
            return ErrorCodes.SUCCESS, content
        except PermissionError as e:
            return ErrorCodes.PERMISSION_DENIED, f"Permission denied reading file '{path}': {str(e)}"
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Unable to read file '{path}': {str(e)}"
