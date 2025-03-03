"""
Tool for viewing file contents
"""

import os
from typing import Dict, Any, Optional

# Tool metadata
TOOL_NAME = "view"
TOOL_DESCRIPTION = "View the contents of a file with optional offset and limit"
TOOL_HELP = """
View the contents of a file.

Usage:
  /view <file_path> [offset=N] [limit=N]
  /view file_path=<path> [offset=N] [limit=N]

Arguments:
  file_path     Path to the file to view (required)
  offset        Number of lines to skip from the beginning (default: 0)
  limit         Maximum number of lines to return (default: 2000)

Examples:
  /view /path/to/file.txt
  /view /path/to/file.txt offset=10 limit=100
  /view file_path=/path/to/file.txt offset=10
"""

TOOL_EXAMPLES = [
    ("/view /etc/passwd", "View the contents of /etc/passwd"),
    ("/view /etc/passwd limit=10", "View only the first 10 lines of /etc/passwd"),
    ("/view file_path=/var/log/syslog offset=100 limit=20", "View 20 lines of /var/log/syslog starting from line 100")
]

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

def _get_help() -> Dict[str, Any]:
    """Return help information for this tool."""
    example_text = "\nExamples:\n" + "\n".join(
        [f"  {example[0]}\n    {example[1]}" for example in TOOL_EXAMPLES]
    )

    return {
        "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{example_text}",
        "error": "",
        "success": True,
        "exit_code": 0
    }

def tool_view(file_path: str = None, offset: int = 0, limit: int = 2000, help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    """
    View the contents of a file with optional offset and limit.

    Args:
        file_path: Path to the file to view
        offset: Number of lines to skip from the beginning
        limit: Maximum number of lines to return
        help: Whether to return help information
        value: Alternative way to specify file_path as positional parameter
        **kwargs: Additional parameters

    Returns:
        Dict with keys: output, error, success, exit_code
    """
    # Return help information if requested
    if help:
        return _get_help()

    # Handle positional parameter
    if file_path is None and value is not None:
        file_path = value

    # Check for missing required parameters
    if file_path is None:
        # Look for positional parameters in kwargs
        for k in kwargs:
            if k.isdigit():
                file_path = kwargs[k]
                break

    if file_path is None:
        return {
            "output": "",
            "error": "Missing required parameter: file_path",
            "success": False,
            "exit_code": 1
        }

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