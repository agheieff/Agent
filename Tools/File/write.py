import os
from Tools.base import Tool, Argument
from Tools.error_codes import ErrorCodes

class WriteFile(Tool):
    def __init__(self):
        super().__init__(
            name="write_file",
            description="Creates a new file with specified content",
            help_text="Creates a new file at the specified path with the provided content. Fails if the file already exists.",
            requires_sudo=False,
            allowed_in_test_mode=True,
            arguments=[
                ("filename", False),  # required
                ("content", False)    # required
            ]
        )
    
    def execute(self, filename, content):
        # Check if path is a directory
        if os.path.isdir(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"'{filename}' is a directory, not a file"
            
        # Check if file already exists
        if os.path.exists(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"File '{filename}' already exists"
        
        # Check if the directory exists
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"Directory '{directory}' does not exist"
        
        try:
            # Create the file and write content
            with open(filename, 'w') as f:
                f.write(content)
            return ErrorCodes.SUCCESS, None
        except PermissionError:
            return ErrorCodes.PERMISSION_DENIED, f"Permission denied when creating file '{filename}'"
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Error creating file: {str(e)}" 