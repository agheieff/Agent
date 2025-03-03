"""
Tool for handling confirmations of operations.
"""
import os
from typing import Dict, Any, Union

# Import from edit_file_tool to share state
from Tools.File.edit_file_tool import _pending_confirmations, _viewed_files

def tool_confirm(confirmation_id: Union[str, int]) -> Dict[str, Any]:
    """
    Confirm a pending operation.

    Args:
        confirmation_id: ID of the operation to confirm

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    try:
        # Convert confirmation_id to integer
        try:
            id_num = int(confirmation_id)
        except ValueError:
            return {
                "output": "",
                "error": f"Invalid confirmation ID: {confirmation_id}",
                "success": False,
                "exit_code": 1
            }

        # Check if confirmation exists
        if id_num not in _pending_confirmations:
            return {
                "output": "",
                "error": f"No pending operation with confirmation ID: {id_num}",
                "success": False,
                "exit_code": 1
            }

        # Get operation details
        operation = _pending_confirmations.pop(id_num)
        operation_type = operation.get("type")

        # Perform the confirmed operation
        if operation_type == "edit":
            # Run the edit operation
            file_path = operation.get("file_path")
            old_string = operation.get("old_string")
            new_string = operation.get("new_string")

            # Mark as viewed to bypass confirmation
            _viewed_files.add(file_path)

            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            # Check for old_string
            if old_string and old_string not in content:
                return {
                    "output": "",
                    "error": f"Target string not found in {file_path}",
                    "success": False,
                    "exit_code": 1
                }

            # Check uniqueness
            if old_string:
                occurrences = content.count(old_string)
                if occurrences > 1:
                    return {
                        "output": "",
                        "error": f"The target string appears {occurrences} times in {file_path}. It must uniquely identify a single instance.",
                        "success": False,
                        "exit_code": 1
                    }

                # Replace exactly one occurrence
                new_content = content.replace(old_string, new_string, 1)
            else:
                # If old_string is empty, replace entire content
                new_content = new_string

            # Write the new content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return {
                "output": f"Confirmed edit: Successfully edited file {file_path}",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        elif operation_type == "replace":
            # Run the replace operation
            file_path = operation.get("file_path")
            content = operation.get("content")

            # Mark as viewed to bypass confirmation
            _viewed_files.add(file_path)

            # Create parent directory if needed
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            # Write the new content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return {
                "output": f"Confirmed replace: Successfully updated file {file_path}",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        else:
            return {
                "output": "",
                "error": f"Unknown operation type: {operation_type}",
                "success": False,
                "exit_code": 1
            }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error confirming operation: {str(e)}",
            "success": False,
            "exit_code": 1
        }

def tool_pending() -> Dict[str, Any]:
    """
    List all pending operations that require confirmation.

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    try:
        if not _pending_confirmations:
            return {
                "output": "No pending operations requiring confirmation",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        output = "Pending operations requiring confirmation:\n\n"

        for id_num, operation in sorted(_pending_confirmations.items()):
            operation_type = operation.get("type", "unknown")
            file_path = operation.get("file_path", "unknown")

            if operation_type == "edit":
                old_string = operation.get("old_string", "")
                new_string = operation.get("new_string", "")
                old_preview = old_string[:20] + "..." if len(old_string) > 20 else old_string
                new_preview = new_string[:20] + "..." if len(new_string) > 20 else new_string

                output += f"ID {id_num}: Edit file {file_path}\n"
                output += f"  Replace: '{old_preview}' with '{new_preview}'\n"

            elif operation_type == "replace":
                content = operation.get("content", "")
                content_preview = content[:30] + "..." if len(content) > 30 else content

                output += f"ID {id_num}: Replace file {file_path}\n"
                output += f"  New content: '{content_preview}'\n"

            else:
                output += f"ID {id_num}: Unknown operation type: {operation_type}\n"

            output += "\n"

        output += "Use '/confirm ID' to approve an operation"

        return {
            "output": output,
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error listing pending operations: {str(e)}",
            "success": False,
            "exit_code": 1
        }
