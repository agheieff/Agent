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
        self.last_read_file = None

    def _run(self, args):
        if not os.path.exists(args['path']):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_NOT_FOUND,
                              message=f"File '{args['path']}' not found")
        if not os.path.isfile(args['path']):
            return ToolResult(success=False, code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                              message=f"Path '{args['path']}' is not a file")
        if not os.access(args['path'], os.R_OK):
            return ToolResult(success=False, code=ErrorCodes.PERMISSION_DENIED,
                              message=f"No read permission for '{args['path']}'")
        try:
            with open(args['path'], 'r') as f:
                if args['lines'] is not None:
                    try:
                        lines = int(args['lines'])
                        content = []
                        for _ in range(lines):
                            line = f.readline()
                            if not line:
                                break
                            content.append(line.rstrip('\n'))
                        content = '\n'.join(content)
                    except ValueError:
                        return ToolResult(success=False, code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                                          message="Invalid line count - must be an integer")
                else:
                    content = f.read().rstrip('\n')
            self.last_read_file = os.path.abspath(args['path'])
            return ToolResult(success=True, code=ErrorCodes.SUCCESS, message=content)
        except PermissionError:
            return ToolResult(success=False, code=ErrorCodes.PERMISSION_DENIED,
                              message="Permission denied when reading file")
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))
