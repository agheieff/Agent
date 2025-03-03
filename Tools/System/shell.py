"""
Tool for executing shell commands.
"""

import os
import asyncio
import subprocess
from typing import Dict, Any, Optional, List, Tuple


TOOL_NAME = "bash"
TOOL_DESCRIPTION = "Execute shell commands in a bash environment"
TOOL_HELP = """
Execute shell commands in a bash environment.

Usage:
  /bash <command>
  /bash command="<command>"

Arguments:
  command        The shell command to execute (required)
  timeout        Maximum execution time in seconds (default: 60)

Notes:
  - The command is executed in a bash shell
  - Standard output and standard error are captured and returned
  - If the command takes too long, it will be terminated
  - Working directory persists between commands
  - Environment variables persist between commands

Examples:
  /bash ls -la
  /bash command="cat /etc/hosts"
  /bash pwd && echo $HOME
  /bash command="find . -name '*.py' | wc -l" timeout=120
"""

TOOL_EXAMPLES = [
    ("/bash ls -la", "List all files in the current directory with details"),
    ("/bash command=\"grep -r 'import' --include='*.py' .\"", "Search for 'import' in all Python files"),
    ("/bash echo 'Hello world' > hello.txt && cat hello.txt", "Create a file and display its contents")
]


_process_env = os.environ.copy()
_working_directory = os.getcwd()

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

async def tool_bash(command: str = None, timeout: int = 60, help: bool = False, value: str = None, **kwargs) -> Dict[str, Any]:
    global _process_env, _working_directory


    if help:
        return _get_help()


    if command is None and value is not None:
        command = value


    if command is None:

        for k in kwargs:
            if k.isdigit():
                command = kwargs[k]
                break

    if command is None:
        return {
            "output": "",
            "error": "Missing required parameter: command",
            "success": False,
            "exit_code": 1
        }

    try:

        try:
            timeout = int(timeout)
            if timeout <= 0:
                timeout = 60
        except (ValueError, TypeError):
            timeout = 60


        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_process_env,
            cwd=_working_directory,
            shell=True
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            return {
                "output": "",
                "error": f"Command timed out after {timeout} seconds",
                "success": False,
                "exit_code": 124                              
            }

        stdout_str = stdout.decode('utf-8', errors='replace')
        stderr_str = stderr.decode('utf-8', errors='replace')


        if 'cd ' in command:


            parts = command.split('cd ')
            for part in parts[1:]:
                dir_path = part.split(';')[0].split('&&')[0].strip()
                if dir_path.startswith('~'):
                    dir_path = os.path.expanduser(dir_path)
                elif not os.path.isabs(dir_path):
                    dir_path = os.path.join(_working_directory, dir_path)

                if os.path.isdir(dir_path):
                    _working_directory = dir_path


        output = stdout_str
        if stderr_str:
            if output:
                output += "\n\nStandard Error:\n" + stderr_str
            else:
                output = stderr_str

        success = process.returncode == 0

        return {
            "output": output,
            "error": stderr_str if not success else "",
            "success": success,
            "exit_code": process.returncode
        }

    except Exception as e:
        return {
            "output": "",
            "error": f"Error executing command: {str(e)}",
            "success": False,
            "exit_code": 1
        }
