import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType

class ReadFile(Tool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description="Reads file contents",
            args=[
                Argument("path", ArgumentType.FILEPATH, "File path"),
                Argument("lines", ArgumentType.INT, "Lines to read", optional=True, default=100)
            ]
        )
        self.last_file = None

    def _run(self, args):
        if not os.path.exists(args['path']):
            return ErrorCodes.RESOURCE_NOT_FOUND, "File not found"
            
        if not os.path.isfile(args['path']):
            return ErrorCodes.INVALID_ARGUMENT_VALUE, "Path is not a file"
            
        if not os.access(args['path'], os.R_OK):
            return ErrorCodes.PERMISSION_DENIED, "No read permission"
            
        try:
            with open(args['path'], 'r') as f:
                content = "".join(f.readlines()[:args['lines']])
            self.last_file = args['path']
            return ErrorCodes.SUCCESS, content
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, str(e)
