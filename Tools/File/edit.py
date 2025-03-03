"""
Tool for editing file contents.
"""
import os
from typing import Dict, Any, Set

# Track which files have been viewed this session
_viewed_files: Set[str] = set()

# Track operations requiring confirmation
_pending_confirmations = {}
_next_confirmation_id = 1

def _ensure_absolute_path(path: str) -> str:
    """Convert a potentially relative path to an absolute path."""
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def tool_edit(file_path: str, old_string: str, new_string: str) -> Dict[str, Any]:
    """
    Edit a file by replacing one occurrence of old_string with new_string.

    Args:
        file_path: Path to the file to edit
        old_string: Text to be replaced (must be unique)
        new_string: Text to replace with

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    global _next_confirmation_id

    try:
        abs_path = _ensure_absolute_path(file_path)

        # If file doesn't exist
        if not os.path.exists(abs_path):
            # If old_string is specified, we expected an existing file
            if old_string:
                return {
                    "output": "",
                    "error": f"File not found: {abs_path}",
                    "success": False,
                    "exit_code": 1
                }
            else:
                # Creating a new file
                parent_dir = os.path.dirname(abs_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)

                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(new_string)

                _viewed_files.add(abs_path)
                return {
                    "output": f"Created new file: {abs_path}",
                    "error": "",
                    "success": True,
                    "exit_code": 0
                }

        # If file exists but hasn't been viewed, require confirmation
        if abs_path not in _viewed_files:
            confirmation_id = _next_confirmation_id
            _next_confirmation_id += 1

            _pending_confirmations[confirmation_id] = {
                "type": "edit",
                "file_path": abs_path,
                "old_string": old_string,
                "new_string": new_string
            }

            return {
                "output": f"Warning: You are about to edit a file that hasn't been viewed: {abs_path}\nUse /confirm {confirmation_id} to proceed or view the file first",
                "error": "",
                "success": True,
                "exit_code": 0,
                "requires_confirmation": True,
                "confirmation_id": confirmation_id
            }

        # File exists and has been viewed, proceed with edit
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        if old_string and old_string not in content:
            return {
                "output": "",
                "error": f"Target string not found in {abs_path}",
                "success": False,
                "exit_code": 1
            }

        # Check for uniqueness of the old_string
        if old_string:
            occurrences = content.count(old_string)
            if occurrences > 1:
                return {
                    "output": "",
                    "error": f"The target string appears {occurrences} times in {abs_path}. It must uniquely identify a single instance.",
                    "success": False,
                    "exit_code": 1
                }
            elif occurrences == 0:
                return {
                    "output": "",
                    "error": f"Target string not found in {abs_path}",
                    "success": False,
                    "exit_code": 1
                }

            # Replace exactly one occurrence
            new_content = content.replace(old_string, new_string, 1)
        else:
            # If old_string is empty, we create or overwrite the file
            new_content = new_string

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        _viewed_files.add(abs_path)
        return {
            "output": f"Successfully edited file: {abs_path}",
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error editing file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
