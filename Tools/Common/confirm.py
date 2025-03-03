"""
Tool for handling confirmations of operations.
"""
import os
from typing import Dict, Any, Union, Optional


TOOL_NAME = "confirm"
TOOL_DESCRIPTION = "Confirm or list pending operations that require verification"
TOOL_HELP = """
Confirm a pending operation that requires verification.

Usage:
  /confirm <confirmation_id>
  /confirm id=<confirmation_id>
  /confirm list

Arguments:
  confirmation_id    ID of the operation to confirm
  list               Flag to list all pending operations requiring confirmation

Examples:
  /confirm 1
  /confirm id=2
  /confirm list
"""

TOOL_EXAMPLES = [
    ("/confirm 1", "Confirm the operation with ID 1"),
    ("/confirm id=2", "Confirm the operation with ID 2"),
    ("/confirm list", "List all pending operations requiring confirmation")
]


_pending_confirmations = {}

def get_pending_confirmations() -> Dict[int, Dict[str, Any]]:
    return _pending_confirmations.copy()

def register_confirmation(id: int, operation_type: str, **params) -> None:
    _pending_confirmations[id] = {
        "type": operation_type,
        **params
    }

def _get_help() -> Dict[str, Any]:
    example_text = "\nExamples:\n" + "\n".join(
        [f"  {example[0]}\n    {example[1]}" for example in TOOL_EXAMPLES]
    )

    return {
        "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{example_text}",
        "error": "",
        "success": True,
        "exit_code": 0
    }

def list_pending() -> Dict[str, Any]:
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

def tool_confirm(id: Union[str, int] = None, list: bool = False, help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:

    if help:
        return _get_help()


    if list:
        return list_pending()


    if id is None and value is not None:
        try:
            id = int(value)
        except (ValueError, TypeError):

            if value.lower() == "list":
                return list_pending()


    if id is None:

        for k in kwargs:
            if k.isdigit():
                try:
                    id = int(kwargs[k])
                    break
                except (ValueError, TypeError):
                    pass


    if id is None:
        return list_pending()

    try:

        try:
            id_num = int(id)
        except ValueError:
            return {
                "output": "",
                "error": f"Invalid confirmation ID: {id}",
                "success": False,
                "exit_code": 1
            }


        if id_num not in _pending_confirmations:
            return {
                "output": "",
                "error": f"No pending operation with confirmation ID: {id_num}",
                "success": False,
                "exit_code": 1
            }


        operation = _pending_confirmations.pop(id_num)
        operation_type = operation.get("type")

        if operation_type == "edit":

            from Tools.File.edit import tool_edit, _viewed_files

            file_path = operation.get("file_path")
            old_string = operation.get("old_string", "")
            new_string = operation.get("new_string", "")


            if hasattr(_viewed_files, "add"):
                _viewed_files.add(file_path)


            result = tool_edit(
                file_path=file_path, 
                old=old_string,
                new=new_string
            )

            if result.get("success", False):
                return {
                    "output": f"Confirmed edit: {result.get('output', '')}",
                    "error": "",
                    "success": True,
                    "exit_code": 0
                }
            else:
                return {
                    "output": "",
                    "error": f"Error executing confirmed edit: {result.get('error', 'Unknown error')}",
                    "success": False,
                    "exit_code": 1
                }

        elif operation_type == "replace":

            from Tools.File.replace import tool_replace, _viewed_files

            file_path = operation.get("file_path")
            content = operation.get("content", "")


            if hasattr(_viewed_files, "add"):
                _viewed_files.add(file_path)


            result = tool_replace(
                file_path=file_path,
                content=content
            )

            if result.get("success", False):
                return {
                    "output": f"Confirmed replace: {result.get('output', '')}",
                    "error": "",
                    "success": True,
                    "exit_code": 0
                }
            else:
                return {
                    "output": "",
                    "error": f"Error executing confirmed replace: {result.get('error', 'Unknown error')}",
                    "success": False,
                    "exit_code": 1
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
