import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ToolResult, ArgumentType

class ReadFile(Tool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description="Reads file contents",
            args=[
                Argument("path", ArgumentType.FILEPATH, "File path"),
                Argument("lines", ArgumentType.INT, "Lines to read", optional=True, default=None)
            ],
            config=ToolConfig(test_mode=True, needs_sudo=False)
        )
        self.last_file = None

    def execute(self, **kwargs):
        try:
            args = self._validate_args(kwargs)
            result = self._run(args)
            return result
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _run(self, args):
        # Validate path exists
        if not os.path.exists(args['path']):
            return ToolResult(
                success=False, 
                code=ErrorCodes.RESOURCE_NOT_FOUND,
                message=f"File '{args['path']}' not found"
            )
            
        # Validate it's a file
        if not os.path.isfile(args['path']):
            return ToolResult(
                success=False, 
                code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                message=f"Path '{args['path']}' is not a file"
            )
            
        # Validate read permissions
        if not os.access(args['path'], os.R_OK):
            return ToolResult(
                success=False, 
                code=ErrorCodes.PERMISSION_DENIED,
                message=f"No read permission for '{args['path']}'"
            )
            
        try:
            with open(args['path'], 'r') as f:
                if args['lines'] is not None:
                    # Handle partial read with line count
                    try:
                        lines = int(args['lines'])
                        content = []
                        for _ in range(lines):
                            line = f.readline()
                            if not line:  # End of file
                                break
                            content.append(line)
                        content = ''.join(content)
                    except ValueError:
                        return ToolResult(
                            success=False,
                            code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                            message="Invalid line count - must be an integer"
                        )
                else:
                    # Full file read
                    content = f.read()
            
            self.last_file = args['path']
            return ToolResult(
                success=True, 
                code=ErrorCodes.SUCCESS, 
                message=content
            )
            
        except PermissionError:
            return ToolResult(
                success=False,
                code=ErrorCodes.PERMISSION_DENIED,
                message="Permission denied when reading file"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                code=ErrorCodes.UNKNOWN_ERROR,
                message=str(e)
            )
