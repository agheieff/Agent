import os
import re
import json
from typing import Dict, Any
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ToolResult, ArgumentType
from Tools.File.read import ReadFile

class EditFile(Tool):
    def __init__(self):
        super().__init__(
            name="edit_file",
            description="Edits a file by replacing patterns",
            args=[
                Argument("filename", ArgumentType.FILEPATH, "File path"),
                Argument("replacements", ArgumentType.STRING, "JSON string with pattern-replacement pairs"),
                Argument("encoding", ArgumentType.STRING, "File encoding", optional=True, default="utf-8")
            ],
            config=ToolConfig(test_mode=True, needs_sudo=False)
        )
        self.read_tool = ReadFile()

    def execute(self, **kwargs):
        try:
            args = self._validate_args(kwargs)
            return self._run(args)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _run(self, args):
        # Validate file existence
        if not os.path.exists(args['filename']):
            return ToolResult(
                success=False,
                code=ErrorCodes.RESOURCE_NOT_FOUND,
                message=f"File '{args['filename']}' not found"
            )
            
        # Validate file is not a directory
        if os.path.isdir(args['filename']):
            return ToolResult(
                success=False,
                code=ErrorCodes.RESOURCE_EXISTS,
                message=f"'{args['filename']}' is a directory"
            )
            
        # Validate read/write permissions
        if not os.access(args['filename'], os.R_OK):
            return ToolResult(
                success=False,
                code=ErrorCodes.PERMISSION_DENIED,
                message=f"No read permission for '{args['filename']}'"
            )
        if not os.access(args['filename'], os.W_OK):
            return ToolResult(
                success=False,
                code=ErrorCodes.PERMISSION_DENIED,
                message=f"No write permission for '{args['filename']}'"
            )
        
        # Check if the file has been read first
        if getattr(self.read_tool, 'last_file', None) != args['filename']:
            return ToolResult(
                success=False,
                code=ErrorCodes.INVALID_OPERATION,
                message=f"File '{args['filename']}' must be read first using read_file"
            )
        
        try:
            # Parse the replacements JSON
            try:
                replacement_dict = json.loads(args['replacements'])
                if not isinstance(replacement_dict, dict):
                    return ToolResult(
                        success=False,
                        code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                        message="Replacements must be a JSON object"
                    )
            except json.JSONDecodeError:
                return ToolResult(
                    success=False,
                    code=ErrorCodes.INVALID_ARGUMENT_VALUE,
                    message="Invalid JSON format for replacements"
                )
            
            # Read the file content
            try:
                with open(args['filename'], 'r', encoding=args['encoding']) as file:
                    content = file.read()
            except UnicodeDecodeError:
                return ToolResult(
                    success=False,
                    code=ErrorCodes.INVALID_OPERATION,
                    message=f"Unable to decode file with encoding '{args['encoding']}'"
                )
            
            # Track changes
            changes_made = 0
            change_summary = []
            
            for pattern, replacement in replacement_dict.items():
                matches = list(re.finditer(re.escape(pattern), content, re.MULTILINE))
                
                if len(matches) == 0:
                    return ToolResult(
                        success=False,
                        code=ErrorCodes.RESOURCE_NOT_FOUND,
                        message=f"Pattern not found: '{pattern}'"
                    )
                elif len(matches) > 1:
                    return ToolResult(
                        success=False,
                        code=ErrorCodes.INVALID_OPERATION,
                        message=f"Pattern '{pattern}' found multiple times ({len(matches)})"
                    )
                
                # Replace the pattern
                content = content.replace(pattern, replacement)
                changes_made += 1
                
                # Record change details
                match = matches[0]
                line_num = content[:match.start()].count('\n') + 1
                change_summary.append(f"Line {line_num}: '{pattern}' -> '{replacement}'")
            
            # Write back the changes
            try:
                with open(args['filename'], 'w', encoding=args['encoding']) as file:
                    file.write(content)
            except Exception as e:
                return ToolResult(
                    success=False,
                    code=ErrorCodes.OPERATION_FAILED,
                    message=f"Error writing file: {str(e)}"
                )
            
            # Return success with change summary
            return ToolResult(
                success=True,
                code=ErrorCodes.SUCCESS,
                message=f"Made {changes_made} replacements:\n" + "\n".join(change_summary)
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                code=ErrorCodes.UNKNOWN_ERROR,
                message=f"Error editing file: {str(e)}"
            )
