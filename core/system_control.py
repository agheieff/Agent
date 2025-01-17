import asyncio
from typing import Tuple

class SystemControl:
    def __init__(self, user: str = None):
        # We'll ignore the user parameter now
        pass

    async def execute_command(self, command: str) -> Tuple[str, str, int]:
        """Execute a shell command with extensive debugging"""
        print(f"\n=== Executing command: {command} ===")
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            print("Process created, waiting for output...")
            stdout, stderr = await process.communicate()
            
            # Debug output
            print(f"Command completed with return code: {process.returncode}")
            if stdout:
                print(f"stdout: {stdout.decode()[:200]}...")
            if stderr:
                print(f"stderr: {stderr.decode()}")
            
            return (
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
                process.returncode
            )
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            print(error_msg)
            return "", error_msg, 1

    async def execute_interactive(self, command: str) -> asyncio.subprocess.Process:
        """
        Start an interactive process (for commands that require interaction)
        Returns the process object for further interaction
        """
        return await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
