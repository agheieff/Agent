import os
from typing import Dict, Any, Optional

def _ensure_absolute_path(path: str) -> str:
    """Convert a potentially relative path to an absolute path."""
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _is_binary_file(file_path: str) -> bool:
    """Check if a file is binary by looking for null bytes."""
    try:
        with open(file_path, 'rb') as f:
            return b'\0' in f.read(4096)
    except:
        return False

def tool_view(file_path: str, offset: int = 0, limit: int = 2000) -> Dict[str, Any]:
    """
    View the contents of a file with optional offset and limit.

    Args:
        file_path: Path to the file to view
        offset: Number of lines to skip from the beginning
        limit: Maximum number of lines to return

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    try:
        abs_path = _ensure_absolute_path(file_path)

        if not os.path.exists(abs_path):
            return {
                "output": "",
                "error": f"File not found: {abs_path}",
                "success": False,
                "exit_code": 1
            }

        if os.path.isdir(abs_path):
            return {
                "output": "",
                "error": f"Path is a directory: {abs_path}",
                "success": False,
                "exit_code": 1
            }

        if _is_binary_file(abs_path):
            return {
                "output": f"[Binary file: {abs_path}]",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            for _ in range(int(offset)):
                next(f, None)

            lines = []
            for _ in range(int(limit)):
                line = next(f, None)
                if line is None:
                    break
                lines.append(line)

            content = ''.join(lines)

            if len(lines) == int(limit) and next(f, None) is not None:
                content += "\n[...file content truncated...]\n"

        return {
            "output": content,
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error reading file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
