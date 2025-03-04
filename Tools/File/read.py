import os
import logging
from typing import Dict, Any

TOOL_NAME = "read"
TOOL_DESCRIPTION = "Read the contents of a text file with optional offset and limit."

logger = logging.getLogger(__name__)

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _is_binary_file(file_path: str) -> bool:
    try:
        with open(file_path, 'rb') as f:
            return b'\0' in f.read(4096)
    except:
        return False

async def tool_read(
    file_path: str,
    offset: int = 0,
    limit: int = 2000,
    **kwargs
) -> Dict[str, Any]:
    """
    Read a file's contents. Return up to `limit` lines after skipping `offset`.
    If the file is binary or unreadable, return a note about that.

    JSON usage example:
    {
      "name": "read",
      "params": {
        "file_path": "/etc/hosts",
        "offset": 10,
        "limit": 50
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
        limit = int(limit)
        if offset < 0 or limit <= 0:
            raise ValueError
    except ValueError:
        return {
            "output": "",
            "error": "Offset must be >= 0 and limit must be > 0 (both integers)",
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

    content_lines = []
    truncated = False
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            # skip offset lines
            for _ in range(offset):
                if not next(f, None):
                    break
            for i in range(limit):
                line = next(f, None)
                if line is None:
                    break
                content_lines.append(line)
            # If there's more lines, we're truncating
            if next(f, None) is not None:
                truncated = True
    except UnicodeDecodeError:
        return {
            "output": f"[Binary or non-text file: {abs_path}]",
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

    info = f"File: {abs_path}\nStarting from line: {offset+1}\nShowing {len(content_lines)} lines"
    if truncated:
        info += " (truncated)\n"
        content_lines.append("[...file content truncated...]")
    else:
        info += " (complete)\n"

    return {
        "output": info + "---\n" + "".join(content_lines),
        "error": "",
        "success": True,
        "exit_code": 0
    }
