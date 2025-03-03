"""
Tool for replacing entire file contents.
"""

import os
import logging
from typing import Dict, Any, Set, Optional

logger = logging.getLogger(__name__)

TOOL_NAME = "replace"
TOOL_DESCRIPTION = "Replace the entire contents of a file with new content"
TOOL_HELP = """
Replace the entire contents of a file with new content.

Usage:
  /replace <file_path> content="<new_content>"
  /replace file_path=<path> content="<new_content>"

Arguments:
  file_path     Path to the file to replace (required)
  content       New content for the file (required)
  mkdir         Whether to create parent directories if they don't exist (default: True)
"""

TOOL_EXAMPLES = [
    ("/replace /path/to/config.json content=\"{\\\"key\\\": \\\"value\\\"}\"", 
     "Replace a JSON configuration file with new content"),
    ("/replace /path/to/script.py content=\"\"\"import os\\n\\nprint(os.getcwd())\\n\"\"\"", 
     "Replace a Python script with multiline content"),
    ("/replace file_path=\"/new/path/file.txt\" content=\"New file content\" mkdir=true", 
     "Create a new file with specified content, creating parent directories")
]

TOOL_NOTES = """
- You must view a file before replacing its contents (for safety)
- If the file doesn't exist, a new file will be created
- This tool will overwrite the entire file content
- Use the edit tool instead if you want to make specific changes
"""

# Set to track files that have been viewed
_viewed_files: Set[str] = set()

# Pending confirmation tracking
_pending_confirmations = {}
_next_confirmation_id = 1

def _ensure_absolute_path(path: str) -> str:
    """Convert relative path to absolute path."""
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _get_help() -> Dict[str, Any]:
    """Generate help information for the tool."""
    example_text = "\nExamples:\n" + "\n".join(
        [f"  {example[0]}\n    {example[1]}" for example in TOOL_EXAMPLES]
    )

    return {
        "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{example_text}\n\n{TOOL_NOTES}",
        "error": "",
        "success": True,
        "exit_code": 0,
        "is_help": True
    }

async def tool_replace(file_path: str = None, content: str = None, mkdir: bool = True,
                  help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    """
    Replace the entire contents of a file.
    
    Args:
        file_path: Path to the file to replace
        content: New content for the file
        mkdir: Whether to create parent directories if needed
        help: Display help information
        value: Positional parameter (file_path)
        **kwargs: Additional keyword arguments
        
    Returns:
        Dictionary with result information
    """
    global _next_confirmation_id

    # Handle help request
    if help:
        return _get_help()

    # Handle positional parameter for file_path
    if file_path is None and value is not None:
        file_path = value

    # Try to get file_path from positional arguments in kwargs
    if file_path is None:
        for k in kwargs:
            if k.isdigit() and int(k) == 0:
                file_path = kwargs[k]
                break

    # Validate required parameters
    if file_path is None:
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

    try:
        abs_path = _ensure_absolute_path(file_path)

        # Check if file exists but hasn't been viewed
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

        # Handle case where parent directory doesn't exist
        parent_dir = os.path.dirname(abs_path)
        if parent_dir and not os.path.exists(parent_dir):
            if mkdir:
                try:
                    os.makedirs(parent_dir, exist_ok=True)
                    logger.info(f"Created directory: {parent_dir}")
                except PermissionError:
                    return {
                        "output": "",
                        "error": f"Permission denied when creating directory: {parent_dir}",
                        "success": False,
                        "exit_code": 1
                    }
                except Exception as e:
                    return {
                        "output": "",
                        "error": f"Error creating directory: {str(e)}",
                        "success": False,
                        "exit_code": 1
                    }
            else:
                return {
                    "output": "",
                    "error": f"Parent directory does not exist: {parent_dir}. Set mkdir=True to create it.",
                    "success": False,
                    "exit_code": 1
                }

        # Write the content to file
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except PermissionError:
            return {
                "output": "",
                "error": f"Permission denied when writing to file: {abs_path}",
                "success": False,
                "exit_code": 1
            }
        except Exception as e:
            return {
                "output": "",
                "error": f"Error writing to file: {str(e)}",
                "success": False,
                "exit_code": 1
            }

        # Add to viewed files
        _viewed_files.add(abs_path)
        
        # Get file stats
        file_size = os.path.getsize(abs_path)
        line_count = content.count('\n') + 1 if content else 0
        
        was_new = not os.path.exists(abs_path)
        
        return {
            "output": f"{'Created' if was_new else 'Replaced'} file: {abs_path}\nSize: {file_size} bytes\nLines: {line_count}",
            "error": "",
            "success": True,
            "exit_code": 0,
            "file_path": abs_path,
            "file_size": file_size,
            "line_count": line_count
        }

    except Exception as e:
        logger.error(f"Error replacing file: {str(e)}")
        return {
            "output": "",
            "error": f"Error replacing file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
