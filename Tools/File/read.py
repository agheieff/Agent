import os
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType

class ReadFile(Tool):
    # Class level variable to keep track of the last read file
    last_read_file = None
    
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="read_file",
            description="Reads a file and returns its contents",
            help_text="Reads a file and returns its contents. Can optionally limit to the first or last N lines.",
            arguments=[
                Argument(
                    name="filename", 
                    arg_type=ArgumentType.FILEPATH,
                    description="Path to the file to read"
                ),
                Argument(
                    name="lines", 
                    arg_type=ArgumentType.INT,
                    is_optional=True, 
                    default_value=100,
                    description="Number of lines to read (0 for all lines)"
                ),
                Argument(
                    name="from_end", 
                    arg_type=ArgumentType.BOOLEAN,
                    is_optional=True, 
                    default_value=False,
                    description="If true, read lines from the end of the file"
                ),
                Argument(
                    name="encoding", 
                    arg_type=ArgumentType.STRING,
                    is_optional=True, 
                    default_value="utf-8",
                    description="File encoding"
                )
            ],
            config=config
        )

    def _execute(self, filename, lines=100, from_end=False, encoding="utf-8"):
        # Validate file existence
        if not os.path.exists(filename):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"File '{filename}' does not exist."
            
        # Validate file is not a directory
        if os.path.isdir(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"'{filename}' is a directory, not a file."
            
        # Validate read permission
        if not os.access(filename, os.R_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No read permission for file '{filename}'."
        
        try:
            # Read the file
            with open(filename, 'r', encoding=encoding) as file:
                # Update the class-level last read file
                ReadFile.last_read_file = filename
                
                if lines == 0:
                    # Read all lines
                    content = file.read()
                    return ErrorCodes.SUCCESS, content
                else:
                    # Read all lines into a list
                    all_lines = file.readlines()
                    total_lines = len(all_lines)
                    
                    # Get the requested number of lines
                    if from_end:
                        # Get the last N lines
                        selected_lines = all_lines[-lines:] if lines < total_lines else all_lines
                    else:
                        # Get the first N lines
                        selected_lines = all_lines[:lines] if lines < total_lines else all_lines
                    
                    # Join the lines
                    content = ''.join(selected_lines)
                    
                    # Add a message about the number of lines shown
                    if lines < total_lines:
                        result = f"{content}\n\nShowing {len(selected_lines)} out of {total_lines} lines."
                    else:
                        result = content
                    
                    return ErrorCodes.SUCCESS, result
                    
        except UnicodeDecodeError:
            return ErrorCodes.INVALID_ARGUMENT_VALUE, f"Unable to decode file with encoding '{encoding}'."
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Error reading file: {str(e)}" 