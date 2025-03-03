"""
Tool for reading file contents.
"""

import os
import logging
from typing import Dict, Any, Optional

TOOL_NAME = "read"
TOOL_DESCRIPTION = "Read the contents of a file with optional offset and limit"
TOOL_HELP = """
Read the contents of a file.

Usage:
  /read <file_path> [offset=N] [limit=N]
  /read file_path=<path> [offset=N] [limit=N]

Arguments:
  file_path     Path to the file to read (required)
  offset        Number of lines to skip from the beginning (default: 0)
  limit         Maximum number of lines to return (default: 2000)
"""

TOOL_EXAMPLES = [
    ("/read /etc/hosts", "Read the contents of /etc/hosts"),
    ("/read /var/log/syslog limit=10", "Read only the first 10 lines of /var/log/syslog"),
    ("/read file_path=/path/to/file.txt offset=100 limit=20", "Read 20 lines of a file starting from line 100")
]

TOOL_NOTES = """
- Binary files are detected and a warning is shown instead of binary content
- The output is truncated if it exceeds the line limit
- Relative paths are resolved relative to the current working directory
"""

logger = logging.getLogger(__name__)

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _is_binary_file(file_path: str) -> bool:
    try:
        with open(file_path, 'rb') as f:
            return b'\0' in f.read(4096)
    except Exception as e:
        logger.error(f"Error checking if file is binary: {e}")
        return False

def _get_help() -> Dict[str, Any]:
    example_text = "\nExamples:\n" + "\n".join(
        [f"  {ex[0]}\n    {ex[1]}" for ex in TOOL_EXAMPLES]
    )
    return {
        "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{example_text}\n\n{TOOL_NOTES}",
        "error": "",
        "success": True,
        "exit_code": 0,
        "is_help": True
    }

async def tool_read(file_path: str = None, offset: int = 0, limit: int = 2000, help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    if help:
        return _get_help()

    if file_path is None and value is not None:
        file_path = value

    if file_path is None:
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

        try:
            offset = int(offset)
            if offset < 0:
                return {
                    "output": "",
                    "error": "Offset must be a non-negative integer",
                    "success": False,
                    "exit_code": 1
                }
        except (ValueError, TypeError):
            return {
                "output": "",
                "error": "Offset must be a valid integer",
                "success": False,
                "exit_code": 1
            }

        try:
            limit = int(limit)
            if limit <= 0:
                return {
                    "output": "",
                    "error": "Limit must be a positive integer",
                    "success": False,
                    "exit_code": 1
                }
        except (ValueError, TypeError):
            return {
                "output": "",
                "error": "Limit must be a valid integer",
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

        truncated = False
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                for _ in range(offset):
                    if next(f, None) is None:
                        break

                lines = []
                for i in range(limit):
                    line = next(f, None)
                    if line is None:
                        break
                    lines.append(line)

                truncated = next(f, None) is not None
                content = ''.join(lines)
                if truncated:
                    content += "\n[...file content truncated...]\n"
        except UnicodeDecodeError:
            return {
                "output": f"[Binary or non-text file: {abs_path}]",
                "error": "",
                "success": True,
                "exit_code": 0
            }

        info = f"File: {abs_path}\n"
        if offset > 0:
            info += f"Starting from line: {offset+1}\n"
        if truncated:
            info += f"Showing {len(lines)} lines (truncated)\n"
        else:
            info += f"Showing {len(lines)} lines (complete file)\n"
        info += "---\n"

        return {
            "output": info + content,
            "error": "",
            "success": True,
            "exit_code": 0,
            "file_path": abs_path,
            "lines_read": len(lines),
            "offset": offset,
            "limit": limit,
            "truncated": truncated
        }

    except Exception as e:
        logger.error(f"Error reading file: {str(e)}")
        return {
            "output": "",
            "error": f"Error reading file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
