"""
A tool that executes arbitrary bash commands without security restrictions.

Usage:
  /bash command="..." [timeout=N]

Examples:
  /bash ls -la
  /bash command="echo 'Hello\nMultiline\nString' > test.txt"
  /bash command="pwd && echo 'Done.'"
  /bash command=\"\"\"echo "Multiline example"
    echo "More lines"
    whoami
  \"\"\"
"""

import asyncio
import subprocess
from typing import Dict, Any, Optional

TOOL_NAME = "bash"
TOOL_DESCRIPTION = "Execute arbitrary bash commands with no security restrictions"
TOOL_HELP = r"""
Execute arbitrary bash commands. No security restrictions are imposed by this tool.

Usage:
  /bash <command>
  /bash command="<command>" [timeout=N]

Arguments:
  command        The shell command to execute (required)
  timeout        Maximum execution time in seconds (default: 60). 0 for no timeout.

Examples:
  /bash ls -la
  /bash command="cat /etc/hosts"
  /bash command="find . -name '*.py' | wc -l" timeout=120
  /bash command=""""""echo "Multiline\nAnother line" > file.sh
  chmod +x file.sh
  ./file.sh""""""
"""

TOOL_EXAMPLES = [
    ("/bash ls -la", "List all files in the current directory with details"),
    ("/bash command=\"echo 'Hello\nMultiline' > multiline.txt\"", "Write a multiline string to a file"),
    ("/bash command=\"pwd && echo Done.\" timeout=30", "Print working directory and a message"),
]

async def tool_bash(command: str = None, timeout: int = 60, help: bool = False,
                    value: str = None, **kwargs) -> Dict[str, Any]:
    if help:
        examples = "\nExamples:\n" + "\n".join(
            [f"  {ex[0]}\n    {ex[1]}" for ex in TOOL_EXAMPLES]
        )
        return {
            "output": f"{TOOL_DESCRIPTION}\n\n{TOOL_HELP}\n{examples}",
            "error": "",
            "success": True,
            "exit_code": 0
        }


    if command is None and value is not None:
        command = value

    if command is None:
        for k in kwargs:
            if k.isdigit():
                command = kwargs[k]
                break

    if not command:
        return {
            "output": "",
            "error": "Missing required parameter: command",
            "success": False,
            "exit_code": 1
        }

    try:

        try:
            timeout = int(timeout)
            if timeout < 0:
                timeout = 60
        except (ValueError, TypeError):
            timeout = 60

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )

        if timeout == 0:

            stdout_bytes, stderr_bytes = await process.communicate()
        else:
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "output": "",
                    "error": f"Command timed out after {timeout} seconds",
                    "success": False,
                    "exit_code": 124
                }

        stdout_str = stdout_bytes.decode('utf-8', errors='replace')
        stderr_str = stderr_bytes.decode('utf-8', errors='replace')
        success = (process.returncode == 0)
        output = stdout_str
        if stderr_str:
            if output:
                output += "\n\n[stderr]:\n" + stderr_str
            else:
                output = stderr_str

        return {
            "output": output,
            "error": "" if success else stderr_str,
            "success": success,
            "exit_code": process.returncode
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error executing bash command: {str(e)}",
            "success": False,
            "exit_code": 1
        }
