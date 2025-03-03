"""
Tool for creating new files with content.
"""

import os
import logging
from typing import Dict, Any, Optional


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
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _get_help() -> Dict[str, Any]:
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

    if content is None:
        return {
            "output": "",
            "error": "Missing required parameter: content",
            "success": False,
            "exit_code": 1
        }

    try:
        abs_path = _ensure_absolute_path(file_path)


        if os.path.exists(abs_path):
            return {
                "output": "",
                "error": f"File already exists: {abs_path}. Use the replace tool to overwrite.",
                "success": False,
                "exit_code": 1
            }


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
