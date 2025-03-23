import os
from Tools.base import Tool

class WriteFile(Tool):
    def __init__(self):
        super().__init__(
            name="write_file",
            description="Creates a new file with specified content",
            help_text="Creates a new file at the specified path with the provided content. Fails if the file already exists.",
            requires_sudo=False,
            allowed_in_test_mode=True
        )
        
        # Add tool-specific exit codes
        self.exit_codes.update({
            1: "File already exists",
            2: "Invalid file path",
            3: "Permission denied",
            4: "Directory does not exist"
        })
    
    def execute(self, filename, content):
        # Check if file already exists
        if os.path.exists(filename):
            return 1, f"File '{filename}' already exists"
        
        # Check if the directory exists
        directory = os.path.dirname(filename)
        if directory and not os.path.exists(directory):
            return 4, f"Directory '{directory}' does not exist"
        
        try:
            # Create the file and write content
            with open(filename, 'w') as f:
                f.write(content)
            return 0, ""
        except IsADirectoryError:
            return 2, f"'{filename}' is a directory, not a file"
        except PermissionError:
            return 3, f"Permission denied when creating file '{filename}'"
        except Exception as e:
            # Return unknown error with the exception message
            return 5, f"Error creating file: {str(e)}" 