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
            return self._execute(**args)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _execute(self, **kwargs):
        return self._run(kwargs)

    def _run(self, args):
        if not os.path.exists(args['filename']):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_NOT_FOUND, 
                              message=f"File '{args['filename']}' does not exist")
        if os.path.isdir(args['filename']):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_EXISTS,
                              message=f"'{args['filename']}' is a directory")
        try:
            os.remove(args['filename'])
            return ToolResult(success=True, code=ErrorCodes.SUCCESS,
                              message=f"File '{args['filename']}' deleted successfully")
        except PermissionError:
            return ToolResult(success=False, code=ErrorCodes.PERMISSION_DENIED,
                              message="No write permission")
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR,
                              message=str(e))
