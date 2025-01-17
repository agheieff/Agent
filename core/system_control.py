import subprocess
import os
import pwd
import asyncio
from typing import Tuple, Optional

class SystemControl:
    def __init__(self, user: str = 'aiagent'):
        self.user = user
        self.uid = pwd.getpwnam(user).pw_uid
        self.gid = pwd.getpwnam(user).pw_gid

    async def execute_command(self, command: str) -> Tuple[str, str, int]:
        """
        Execute a shell command as the AI agent user
        Returns: (stdout, stderr, return_code)
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=self._switch_user
            )
            
            stdout, stderr = await process.communicate()
            
            return (
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
                process.returncode
            )
        except Exception as e:
            return "", str(e), 1

    def _switch_user(self):
        """Switch to the AI agent user before executing commands"""
        os.setgid(self.gid)
        os.setuid(self.uid)

    async def execute_interactive(self, command: str) -> asyncio.subprocess.Process:
        """
        Start an interactive process (for commands that require interaction)
        Returns the process object for further interaction
        """
        return await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=self._switch_user
        )
