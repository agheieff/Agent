import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ToolResult, ArgumentType

class DeleteFile(Tool):
    def __init__(self):
        super().__init__(
            name="delete_file",
            description="Deletes a file",
            args=[
                Argument("filename", ArgumentType.FILEPATH, "File path"),
                Argument("force", ArgumentType.BOOLEAN, "Force delete", optional=True, default=False)
            ],
            config=ToolConfig(test_mode=True, needs_sudo=False)
        )

    def execute(self, **kwargs):
        try:
            args = self._validate_args(kwargs)
            return self._run(args)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _run(self, args):
        if not os.path.exists(args['filename']):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_NOT_FOUND, 
                            message=f"File '{args['filename']}' not found")
            
        if os.path.isdir(args['filename']):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_EXISTS,
                            message=f"'{args['filename']}' is a directory")
            
        try:
            os.remove(args['filename'])
            return ToolResult(success=True, code=ErrorCodes.SUCCESS,
                            message=f"File '{args['filename']}' deleted")
        except PermissionError:
            return ToolResult(success=False, code=ErrorCodes.PERMISSION_DENIED,
                            message="Permission denied")
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.OPERATION_FAILED,
                            message=str(e))
