"""
Tool for editing file contents (replace a unique occurrence of `old` with `new`).
Now includes examples for multiline usage.
"""
import os
from typing import Dict, Any, Set, Optional

TOOL_NAME = "edit"
TOOL_DESCRIPTION = "Edit a file by replacing a specific string with a new one"
TOOL_HELP = """
Edit a file by replacing a specific string with a new one.

Usage:
  /edit <file_path> old="<old_string>" new="<new_string>"
  /edit file_path=<path> old="<old_string>" new="<new_string>"

Arguments:
  file_path     Path to the file to edit (required)
  old           Text to be replaced (required, must be unique in the file)
  new           New text to replace with (required)

Notes:
  - The `old` string must match exactly, including all whitespace
  - The `old` string must uniquely identify a single location in the file
  - If `old` is empty and file does not exist, a new file is created with content = `new`
  - If file does not exist but `old` is not empty, it will raise an error (since there's nowhere to replace)
  - For multiline replacements, use triple quotes:
    /edit file_path=/tmp/code.py old=\"\"\"class Foo:\"\"\" new=\"\"\"class Foo:\n    def bar(self):\n        pass\n\"\"\"

Examples:
  /edit /path/to/file.txt old="Hello World" new="Hello Universe"
  /edit file_path="/etc/hosts" old="127.0.0.1 localhost" new="127.0.0.1 localhost myhost"
  /edit file_path="/some_file.py" old=\"\"\"def hello():\n    pass\"\"\" new=\"\"\"def hello():\n    print('Hi!')\"\"\"
"""

TOOL_EXAMPLES = [
    ("/edit /path/to/file.py old=\"def hello():\" new=\"def hello_world():\"",
     "Rename a function in a Python file"),
    ("/edit /path/to/config.json old=\"\\\"port\\\": 8080\" new=\"\\\"port\\\": 9090\"",
     "Change a port number in a JSON configuration file"),
    ("/edit file_path=\"/new_file.txt\" old=\"\" new=\"This is a new file\"",
     "Create a new file with initial content"),
    ("/edit file_path=\"/tmp/code.py\" old=\"\"\"def foo():\n    pass\"\"\" new=\"\"\"def foo():\n    print('Updated!')\"\"\"",
     "Multiline replacement in code file"),
]

_viewed_files: Set[str] = set()
_pending_confirmations = {}
_next_confirmation_id = 1

def _ensure_absolute_path(path: str) -> str:
    if not os.path.isabs(path):
        return os.path.abspath(os.path.join(os.getcwd(), path))
    return path

def _get_help() -> Dict[str, Any]:
    example_text = "\nExamples:\n" + "\n".join(
        [f"  {example[0]}\n    {example[1]}" for example in TOOL_EXAMPLES]
    )

    return {
        "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{example_text}",
        "error": "",
        "success": True,
        "exit_code": 0
    }

def tool_edit(file_path: str = None, old: str = None, new: str = None,
              old_string: str = None, new_string: str = None,
              help: bool = False, **kwargs) -> Dict[str, Any]:
    global _next_confirmation_id

    if help:
        return _get_help()


    if file_path is None:
        for k in kwargs:

            if k.isdigit() and int(k) == 0:
                file_path = kwargs[k]
                break

    if old is None and old_string is not None:
        old = old_string
    if new is None and new_string is not None:
        new = new_string

    if file_path is None:
        return {
            "output": "",
            "error": "Missing required parameter: file_path",
            "success": False,
            "exit_code": 1
        }

    if old is None:
        return {
            "output": "",
            "error": "Missing required parameter: old or old_string",
            "success": False,
            "exit_code": 1
        }

    if new is None:
        return {
            "output": "",
            "error": "Missing required parameter: new or new_string",
            "success": False,
            "exit_code": 1
        }

    try:
        abs_path = _ensure_absolute_path(file_path)


        if not os.path.exists(abs_path) and old != "":
            return {
                "output": "",
                "error": f"File not found: {abs_path}",
                "success": False,
                "exit_code": 1
            }
        elif not os.path.exists(abs_path) and old == "":

            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new)
            _viewed_files.add(abs_path)
            return {
                "output": f"Created new file: {abs_path}",
                "error": "",
                "success": True,
                "exit_code": 0
            }


        if abs_path not in _viewed_files:
            confirmation_id = _next_confirmation_id
            _next_confirmation_id += 1

            _pending_confirmations[confirmation_id] = {
                "type": "edit",
                "file_path": abs_path,
                "old_string": old,
                "new_string": new
            }

            return {
                "output": f"Warning: You are about to edit a file that hasn't been viewed: {abs_path}\nUse /confirm {confirmation_id} to proceed or view the file first",
                "error": "",
                "success": True,
                "exit_code": 0,
                "requires_confirmation": True,
                "confirmation_id": confirmation_id
            }


        with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        if old and old not in content:
            return {
                "output": "",
                "error": f"Target string not found in {abs_path}",
                "success": False,
                "exit_code": 1
            }

        occurrences = content.count(old)
        if occurrences > 1:
            return {
                "output": "",
                "error": f"The target string appears {occurrences} times in {abs_path}. It must uniquely identify a single instance.",
                "success": False,
                "exit_code": 1
            }
        elif occurrences == 0:
            return {
                "output": "",
                "error": f"Target string not found in {abs_path}",
                "success": False,
                "exit_code": 1
            }

        new_content = content.replace(old, new, 1)

        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        _viewed_files.add(abs_path)
        return {
            "output": f"Successfully edited file: {abs_path}",
            "error": "",
            "success": True,
            "exit_code": 0
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error editing file: {str(e)}",
            "success": False,
            "exit_code": 1
        }
