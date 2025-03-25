import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType

class WriteFile(Tool):
    def __init__(self):
        super().__init__(
            name="write_file",
            description="Writes content to a file",
            args=[
                Argument("path", ArgumentType.FILEPATH, "File path"),
                Argument("content", ArgumentType.STRING, "Content to write"),
                Argument("overwrite", ArgumentType.BOOLEAN, "Overwrite if exists", optional=True, default=False)
            ]
        )

    def execute(self, **kwargs):
        try:
            args = self._validate_args(kwargs)
            return self._run(args)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _run(self, args):
        if os.path.isdir(args['path']):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_EXISTS,
                            message=f"'{args['path']}' is a directory")
            
        dirname = os.path.dirname(args['path']) or '.'
        if not os.path.exists(dirname):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_NOT_FOUND,
                            message=f"Directory '{dirname}' does not exist")
            
        if not os.access(dirname, os.W_OK):
            return ToolResult(success=False, code=ErrorCodes.PERMISSION_DENIED,
                            message=f"No write permission in '{dirname}'")
            
        if os.path.exists(args['path']) and not args['overwrite']:
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_EXISTS,
                            message=f"File '{args['path']}' exists and overwrite=False")
            
        try:
            with open(args['path'], 'w') as f:
                f.write(args['content'])
            return ToolResult(success=True, code=ErrorCodes.SUCCESS)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.OPERATION_FAILED,
                            message=str(e))
