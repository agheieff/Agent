import os
import re
from typing import List, Dict, Tuple
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType
from Tools.File.read import ReadFile

class EditFile(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="edit_file",
            description="Edits a file by replacing patterns",
            help_text="Edits a file by replacing one or more patterns. The file must have been read first using read_file.",
            arguments=[
                Argument(
                    name="filename", 
                    arg_type=ArgumentType.FILEPATH,
                    description="Path to the file to edit"
                ),
                Argument(
                    name="replacements", 
                    arg_type=ArgumentType.STRING,
                    description="JSON string with patterns and replacements in format {\"pattern1\": \"replacement1\", ...}"
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

    def _execute(self, filename, replacements, encoding="utf-8"):
        import json
        
        # Validate file existence
        if not os.path.exists(filename):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"File '{filename}' does not exist."
            
        # Validate file is not a directory
        if os.path.isdir(filename):
            return ErrorCodes.RESOURCE_EXISTS, f"'{filename}' is a directory, not a file."
            
        # Validate read/write permissions
        if not os.access(filename, os.R_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No read permission for file '{filename}'."
        if not os.access(filename, os.W_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No write permission for file '{filename}'."
        
        # Check if the file has been read first
        read_tool = ReadFile()
        if read_tool.last_read_file != filename:
            return ErrorCodes.INVALID_OPERATION, f"File '{filename}' has not been read first. Use read_file tool before editing."
        
        try:
            # Parse the replacements JSON
            try:
                replacement_dict = json.loads(replacements)
                if not isinstance(replacement_dict, dict):
                    return ErrorCodes.INVALID_ARGUMENT_VALUE, "Replacements must be a JSON object with pattern-replacement pairs."
            except json.JSONDecodeError:
                return ErrorCodes.INVALID_ARGUMENT_VALUE, "Invalid JSON format for replacements."
            
            # Read the file content
            try:
                with open(filename, 'r', encoding=encoding) as file:
                    content = file.read()
            except UnicodeDecodeError:
                return ErrorCodes.INVALID_ARGUMENT_VALUE, f"Unable to decode file with encoding '{encoding}'."
            
            # Track changes and ensure each pattern matches exactly once
            changes_made = 0
            change_summary = []
            
            # Process each replacement
            for pattern, replacement in replacement_dict.items():
                # Find all occurrences of the pattern
                matches = list(re.finditer(re.escape(pattern), content, re.MULTILINE))
                
                # Validate exactly one match
                if len(matches) == 0:
                    return ErrorCodes.RESOURCE_NOT_FOUND, f"Pattern not found: '{pattern}'"
                elif len(matches) > 1:
                    return ErrorCodes.INVALID_OPERATION, f"Pattern '{pattern}' found multiple times ({len(matches)}). Each pattern must match exactly once."
                
                # Replace the pattern
                content = content.replace(pattern, replacement)
                changes_made += 1
                
                # Track the change
                match = matches[0]
                line_num = content[:match.start()].count('\n') + 1
                change_summary.append(f"Line {line_num}: '{pattern}' -> '{replacement}'")
            
            # Write the modified content back to the file
            with open(filename, 'w', encoding=encoding) as file:
                file.write(content)
            
            # Return success message with summary
            summary = "\n".join(change_summary)
            return ErrorCodes.SUCCESS, f"Successfully made {changes_made} replacements:\n{summary}"
            
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Error editing file: {str(e)}" 