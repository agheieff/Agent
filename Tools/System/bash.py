import asyncio
import subprocess
from typing import Dict, Any

TOOL_NAME = "bash"
TOOL_DESCRIPTION = "Execute arbitrary shell (bash) commands, with optional timeout."

EXAMPLES = {
    "command": "ls -la /tmp",
    "timeout": 60
}

FORMATTER = "command"

async def tool_bash(
    command: str,
    timeout: int = 60,
    **kwargs
) -> Dict[str, Any]:
    if not command:
        return {
            "output": "",
            "error": "Missing required parameter: command",
            "success": False,
            "exit_code": 1
        }

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
                    "exit_code": 124,
                    "command": command
                }
        else:
            stdout_bytes, stderr_bytes = await process.communicate()

        stdout_str = stdout_bytes.decode('utf-8', errors='replace')
        stderr_str = stderr_bytes.decode('utf-8', errors='replace')
        success = (process.returncode == 0)
        exit_code = process.returncode

        if success:

            return {
                "output": f"Command executed (exit={exit_code}): {command}",
                "error": "",
                "success": True,
                "exit_code": exit_code,
                "command": command,
                "stdout": stdout_str,
                "stderr": stderr_str
            }
        else:
            return {
                "output": "",
                "error": f"Command failed (exit={exit_code}): {stderr_str}",
                "success": False,
                "exit_code": exit_code,
                "command": command,
                "stdout": stdout_str,
                "stderr": stderr_str
            }
    except Exception as e:
        return {
            "output": "",
            "error": f"Error executing bash command: {str(e)}",
            "success": False,
            "exit_code": 1,
            "command": command
        }
