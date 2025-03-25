import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType

class DeleteFile(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="delete_file",
            description="Deletes a file",
            help_text="Deletes a file from the filesystem.",
            arguments=[
                Argument(
                    name="filename", 
                    arg_type=ArgumentType.FILEPATH,
                    description="Path to the file to delete"
                ),
                Argument(
                    name="force", 
                    arg_type=ArgumentType.BOOLEAN,
                    is_optional=True, 
                    default_value=False,
                    description="If true, suppresses confirmation prompt"
                )
            ],
            config=config
        )

    def _execute(self, filename, force=False):
        # Validate file existence
        if not os.path.exists(filename):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"File '{filename}' does not exist."
            
        # Validate file is not a directory
        if os.path.isdir(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"'{filename}' is a directory, not a file. Use a directory removal tool instead."
            
        # Validate write permission on the directory (needed to delete)
        directory = os.path.dirname(filename) or '.'
        if not os.access(directory, os.W_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No write permission in directory '{directory}'."
        
        try:
            # Delete the file
            os.remove(filename)
            return ErrorCodes.SUCCESS, f"File '{filename}' deleted successfully."
            
        except PermissionError:
            return ErrorCodes.PERMISSION_DENIED, f"Permission denied when deleting file '{filename}'."
        except OSError as e:
            return ErrorCodes.OPERATION_FAILED, f"OS error when deleting file '{filename}': {e.strerror}"
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Unexpected error: {str(e)}"
