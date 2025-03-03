"""
Tool for replacing entire file contents.
"""
import os
from typing import Dict, Any, Set

# Import from edit_file_tool to share state
from Tools.File.edit_file_tool import _viewed_files, _pending_confirmations, _next_confirmation_id, _ensure_absolute_path

def tool_replace(file_path: str, content: str) -> Dict[str, Any]:
    """
    Replace the entire content of a file.

    Args:
        file_path: Path to the file
        content: New content for the file

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    global _next_confirmation_id

    try:
        abs_path = _ensure_absolute_path(file_path)

        # If file exists and not viewed, require confirmation
        if os.path.exists(abs_path) and abs_path not in _viewed_files:
            confirmation_id = _next_confirmation_id
            _next_confirmation_id += 1

            _pending_confirmations[confirmation_id] = {
                "type": "replace",
                "file_path": abs_path,
                "content": content
            }

            return {
                "output": f"Warning: You are about to replace a file that hasn't been viewed: {abs_path}\nUse /confirm {confirmation_id} to proceed or view the file first",
                "error": "",
                "success": True,
                "exit_code": 0,
                "requires_confirmation": True,
                "confirmation_id": confirmation_id
            }

        # Create parent directory if needed
        parent_dir = os.path.dirname(abs_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)

        _viewed_files.add(abs_path)
        return {
            "output": f"Updated file: {abs_path}",
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error replacing file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
