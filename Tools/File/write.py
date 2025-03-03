"""
Tool for creating new files with content.
"""

import os
import logging
from typing import Dict, Any, Optional

# Tool metadata
TOOL_NAME = "write"
TOOL_DESCRIPTION = "Create a new file with the specified content"
TOOL_HELP = """
Create a new file with the specified content. Will not overwrite existing files.

Usage:
  /write <file_path> content="file content"
  /write file_path=<path> content="file content"
  /write file_path=<path> content="""multiline
  content goes
  here"""

Arguments:
  file_path     Path to the new file to create (required)
  content       Content to write to the file (required)
  mkdir         Whether to create parent directories if they don't exist (default: True)
"""

TOOL_EXAMPLES = [
    ("/write /tmp/hello.txt content=\"Hello, world!\"", "Create a file with a simple message"),
    ("/write file_path=\"data/config.json\" content=\"{\\\"key\\\": \\\"value\\\"}\"", "Create a JSON configuration file"),
    ("/write file_path=\"script.py\" content=\"\"\"import os\nprint(os.getcwd())\n\"\"\"", "Create a Python script with multiline content")
]

TOOL_NOTES = """
- This tool only creates new files and will not overwrite existing files
- To overwrite existing files, use the replace tool instead
- Parent directories will be created by default if they don't exist
- Multiline content can be specified using triple quotes: content=\"\"\"multiple lines\"\"\"
"""

logger = logging.getLogger(__name__)

def _ensure_absolute_path(path: str) -> str:
    """Convert a potentially relative path to an absolute path."""
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _get_help() -> Dict[str, Any]:
    """Return help information for this tool."""
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

async def tool_write(file_path: str = None, content: str = None, mkdir: bool = True, 
                    help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    """
    Create a new file with the specified content.

    Args:
        file_path: Path to the new file to create
        content: Content to write to the file
        mkdir: Whether to create parent directories if they don't exist
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

    # Check for required parameters
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

        # Check if file already exists
        if os.path.exists(abs_path):
            return {
                "output": "",
                "error": f"File already exists: {abs_path}. Use the replace tool to overwrite.",
                "success": False,
                "exit_code": 1
            }

        # Create parent directory if it doesn't exist
        parent_dir = os.path.dirname(abs_path)
        if not os.path.exists(parent_dir):
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

        # Write content to file
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

        # Get file stats for output
        file_size = os.path.getsize(abs_path)
        line_count = content.count('\n') + 1 if content else 0

        return {
            "output": f"Created file: {abs_path}\nSize: {file_size} bytes\nLines: {line_count}",
            "error": "",
            "success": True,
            "exit_code": 0,
            "file_path": abs_path,
            "file_size": file_size,
            "line_count": line_count
        }

    except Exception as e:
        logger.error(f"Error creating file: {str(e)}")
        return {
            "output": "",
            "error": f"Error creating file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
