import os
import logging
from typing import Dict, Any

TOOL_NAME = "read"
TOOL_DESCRIPTION = "Read the contents of a text file with optional offset and limit."
EXAMPLES = {
    "file_path": "/etc/hosts",
    "offset": 0,
    "limit": 2000
}
FORMATTER = "file_content"
logger = logging.getLogger(__name__)

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _is_binary_file(file_path: str) -> bool:
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(4096)
            return b'\0' in chunk
    except:
        return False

async def tool_read(file_path: str, offset: int = 0, limit: int = 2000, **kwargs) -> Dict[str, Any]:
    if not file_path:
        return {
            "output": "",
            "error": "Missing required parameter: file_path",
            "exit_code": 1
        }
    abs_path = _ensure_absolute_path(file_path)
    if not os.path.exists(abs_path):
        return {
            "output": "",
            "error": f"File not found: {abs_path}",
            "exit_code": 1,
            "file_path": abs_path
        }
    if os.path.isdir(abs_path):
        return {
            "output": "",
            "error": f"Path is a directory: {abs_path}",
            "exit_code": 1,
            "file_path": abs_path
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
            "exit_code": 1
        }
    if _is_binary_file(abs_path):
        return {
            "output": f"Binary file: {abs_path}",
            "error": "",
            "exit_code": 0,
            "file_path": abs_path,
            "binary": True
        }
    content_lines = []
    truncated = False
    try:
        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            # Skip lines up to offset
            for _ in range(offset):
                if not next(f, None):
                    break
            for _ in range(limit):
                line = next(f, None)
                if line is None:
                    break
                content_lines.append(line)
            if next(f, None) is not None:
                truncated = True
    except Exception as e:
        return {
            "output": "",
            "error": f"Error reading file: {str(e)}",
            "exit_code": 1,
            "file_path": abs_path
        }
    read_count = len(content_lines)
    short_info = f"Read {read_count} lines from {abs_path}"
    if truncated:
        short_info += " (truncated)"
    return {
        "output": short_info,
        "error": "",
        "exit_code": 0,
        "file_path": abs_path,
        "content": "".join(content_lines),
        "truncated": truncated,
        "binary": False,
        "line_count": read_count,
        "offset": offset
    }

def display_format(params: Dict[str, Any], result: Dict[str, Any]) -> str:
    if result.get("exit_code", 1) == 0:
        info = result.get("output", "")
        if result.get("truncated", False):
            info += " [truncated]"
        return f"[READ] {info}"
    else:
        return f"[READ] Error: {result.get('error', 'Unknown error')}"
