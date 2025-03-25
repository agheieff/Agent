from Tools.base import Tool, Argument, ArgumentType, ToolConfig, ToolResult, ErrorCode
import os

class ReadFile(Tool):
    def __init__(self):
        super().__init__(
            name="read_file",
            description="Reads contents of a file",
            args=[
                Argument("path", ArgumentType.FILEPATH, "Path to file"),
                Argument("lines", ArgumentType.INT, "Number of lines to read", 
                        is_optional=True, default=100)
            ],
            config=ToolConfig()
        )
    
    def _run(self, args) -> ToolResult:
        path = os.path.expanduser(args['path'])
        with open(path, 'r') as f:
            content = ''.join(f.readlines()[:args['lines']])
        return ToolResult(ErrorCode.SUCCESS, content)
