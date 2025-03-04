import os
import logging
from typing import Dict, Any

TOOL_NAME = "write"
TOOL_DESCRIPTION = "Create a new file with specified content (will not overwrite existing)."

logger = logging.getLogger(__name__)

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

async def tool_write(
    file_path: str,
    content: str,
    mkdir: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    Create a new file. Fails if file already exists.
    JSON usage example:
    {
      "name": "write",
      "params": {
        "file_path": "/tmp/new_file.txt",
        "content": "Hello world",
        "mkdir": true
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
    if content is None:
        return {
            "output": "",
            "error": "Missing required parameter: content",
            "success": False,
            "exit_code": 1
        }

    abs_path = _ensure_absolute_path(file_path)
    if os.path.exists(abs_path):
        return {
            "output": "",
            "error": f"File already exists: {abs_path}",
            "success": False,
            "exit_code": 1
        }

    parent_dir = os.path.dirname(abs_path)
    if parent_dir and not os.path.exists(parent_dir):
        if mkdir:
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except Exception as e:
                return {
                    "output": "",
                    "error": f"Error creating parent directory: {str(e)}",
                    "success": False,
                    "exit_code": 1
                }
        else:
            return {
                "output": "",
                "error": f"Parent directory does not exist: {parent_dir}",
                "success": False,
                "exit_code": 1
            }

    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        file_size = os.path.getsize(abs_path)
        return {
            "output": f"Created file: {abs_path} (size: {file_size} bytes)",
            "error": "",
            "success": True,
            "exit_code": 0
        }
    except Exception as e:
        return {
            "output": "",
            "error": f"Error writing file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
