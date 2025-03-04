import os
from typing import Dict, Any

TOOL_NAME = "edit"
TOOL_DESCRIPTION = "Edit a file by replacing a unique occurrence of `old` with `new`."
EXAMPLES = {
    "file_path": "/tmp/config.txt",
    "old": "version=1.0",
    "new": "version=2.0"
}
FORMATTER = "file_operation"

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def tool_edit(file_path: str, old: str, new: str, **kwargs) -> Dict[str, Any]:
    if not file_path:
        return {
            "output": "",
            "error": "Missing required parameter: file_path",
            "exit_code": 1
        }
    if old is None:
        return {
            "output": "",
            "error": "Missing required parameter: old",
            "exit_code": 1
        }
    if new is None:
        return {
            "output": "",
            "error": "Missing required parameter: new",
            "exit_code": 1
        }
    abs_path = _ensure_absolute_path(file_path)
    if not os.path.exists(abs_path):
        # If 'old' is empty, create new file.
        if old == "":
            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.exists(parent_dir):
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                except Exception as e:
                    return {
                        "output": "",
                        "error": f"Error creating parent directory: {str(e)}",
                        "exit_code": 1,
                        "file_path": abs_path
                    }
            try:
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(new)
                return {
                    "output": f"Created new file: {abs_path}",
                    "error": "",
                    "exit_code": 0,
                    "file_path": abs_path
                }
            except Exception as e:
                return {
                    "output": "",
                    "error": f"Error creating new file: {str(e)}",
                    "exit_code": 1,
                    "file_path": abs_path
                }
        else:
            return {
                "output": "",
                "error": f"File not found: {abs_path}",
                "exit_code": 1,
                "file_path": abs_path
            }
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return {
            "output": "",
            "error": f"Error reading file: {str(e)}",
            "exit_code": 1,
            "file_path": abs_path
        }
    occurrences = content.count(old)
    if occurrences == 0:
        return {
            "output": "",
            "error": f"Target string not found in {abs_path}",
            "exit_code": 1,
            "file_path": abs_path
        }
    if occurrences > 1:
        return {
            "output": "",
            "error": f"Target string appears {occurrences} times in {abs_path}. Must be unique.",
            "exit_code": 1,
            "file_path": abs_path
        }
    new_content = content.replace(old, new, 1)
    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return {
            "output": f"Edited file: {abs_path}",
            "error": "",
            "exit_code": 0,
            "file_path": abs_path
        }
    except Exception as e:
        return {
            "output": "",
            "error": f"Error writing updated file: {str(e)}",
            "exit_code": 1,
            "file_path": abs_path
        }

def display_format(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    file_path = result.get("file_path", "")
    if result.get("exit_code", 1) == 0:
        return f"[EDIT] Success: {file_path}"
    else:
        return f"[EDIT] Error: {result.get('error', 'Unknown error')}"
