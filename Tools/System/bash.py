import asyncio
import subprocess
from typing import Dict, Any

TOOL_NAME = "bash"
TOOL_DESCRIPTION = "Execute arbitrary shell (bash) commands, with optional timeout."

async def tool_bash(
    command: str,
    timeout: int = 60,
    **kwargs
) -> Dict[str, Any]:
    """
    Execute a shell command. JSON usage example:
    {
      "name": "bash",
      "params": {
        "command": "echo Hello && ls -la",
        "timeout": 30
      }
    }

    If timeout=0, no timeout is enforced.
    """
    if not command:
        return {
            "output": "",
            "error": "Missing required parameter: command",
            "success": False,
            "exit_code": 1
        }

    # create subprocess
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        if timeout and timeout > 0:
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return {
                    "output": "",
                    "error": f"Command timed out after {timeout} seconds",
                    "success": False,
                    "exit_code": 124
                }
        else:
            stdout_bytes, stderr_bytes = await process.communicate()

        stdout_str = stdout_bytes.decode('utf-8', errors='replace')
        stderr_str = stderr_bytes.decode('utf-8', errors='replace')
        success = (process.returncode == 0)
        output = stdout_str
        if stderr_str:
            if output:
                output += "\n[stderr]:\n" + stderr_str
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
