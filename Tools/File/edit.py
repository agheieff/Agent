import os
from typing import Dict, Any

TOOL_NAME = "edit"
TOOL_DESCRIPTION = "Edit a file by replacing a unique occurrence of `old` with `new`."

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def tool_edit(
    file_path: str,
    old: str,
    new: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Edit a file by replacing exactly one occurrence of `old` with `new`.
    If `old` is empty and the file does not exist, create a new file with `new`.
    JSON usage example:
    {
      "name": "edit",
      "params": {
        "file_path": "/path/to/file.txt",
        "old": "Hello World",
        "new": "Hello Universe"
      }
    }
    """
    if not file_path:
        return {
            "output": "",
            "error": "Missing required parameter: file_path",
            "success": False,
            "exit_code": 1
        }
    if old is None:
        return {
            "output": "",
            "error": "Missing required parameter: old",
            "success": False,
            "exit_code": 1
        }
    if new is None:
        return {
            "output": "",
            "error": "Missing required parameter: new",
            "success": False,
            "exit_code": 1
        }

    abs_path = _ensure_absolute_path(file_path)
    if not os.path.exists(abs_path):
        # If old=="" we create new file with 'new' as content
        if old == "":
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            try:
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(new)
                return {
                    "output": f"Created new file: {abs_path}",
                    "error": "",
                    "success": True,
                    "exit_code": 0
                }
            except Exception as e:
                return {
                    "output": "",
                    "error": f"Error creating new file: {str(e)}",
                    "success": False,
                    "exit_code": 1
                }
        else:
            return {
                "output": "",
                "error": f"File not found: {abs_path}",
                "success": False,
                "exit_code": 1
            }

    # read file
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return {
            "output": "",
            "error": f"Error reading file: {str(e)}",
            "success": False,
            "exit_code": 1
        }

    # check uniqueness
    occurrences = content.count(old)
    if occurrences == 0:
        return {
            "output": "",
            "error": f"Target string not found in {abs_path}",
            "success": False,
            "exit_code": 1
        }
    if occurrences > 1:
        return {
            "output": "",
            "error": f"Target string appears {occurrences} times in {abs_path}. Must be unique.",
            "success": False,
            "exit_code": 1
        }

    # replace once
    new_content = content.replace(old, new, 1)
    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {
            "output": f"Successfully edited file: {abs_path}",
            "error": "",
            "success": True,
            "exit_code": 0
        }
    except Exception as e:
        return {
            "output": "",
            "error": f"Error writing updated file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
