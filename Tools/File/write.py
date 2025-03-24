import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType

class WriteFile(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="write_file",
            description="Creates a new file with specified content",
            help_text="Creates a new file at the specified path with the provided content. Fails if the file already exists.",
            arguments=[
                Argument(
                    name="filename", 
                    arg_type=ArgumentType.FILEPATH,
                    description="Path where the file should be created"
                ),
                Argument(
                    name="content",
                    arg_type=ArgumentType.STRING,
                    description="Content to write to the file"
                )
            ],
            config=config
        )

    def _execute(self, filename, content, encoding='utf-8'):
        # Validate if target is a directory
        if os.path.isdir(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"'{filename}' is a directory."

        # Validate if file already exists
        if os.path.exists(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"File '{filename}' already exists."

        # Validate directory existence and permissions
        directory = os.path.dirname(filename) or '.'
        if not os.path.exists(directory):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"Directory '{directory}' does not exist."

        if not os.access(directory, os.W_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No write permission in directory '{directory}'."

        # Attempt to create and write to file
        try:
            with open(filename, 'w', encoding=encoding) as file:
                file.write(content)
            return ErrorCodes.SUCCESS, None
        except PermissionError:
            return ErrorCodes.PERMISSION_DENIED, f"Permission denied when writing to '{filename}'."
        except OSError as e:
            return ErrorCodes.OPERATION_FAILED, f"OS error when writing file '{filename}': {e.strerror}"
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Unexpected error: {str(e)}"