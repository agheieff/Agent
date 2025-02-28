import asyncio
import logging
from typing import Tuple
from pathlib import Path
import json
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class StructuredOutput:
    """Represents structured output from shell commands"""
    raw_output: str
    data: str
    format_type: str = 'plain'

    def to_json(self) -> str:
        return json.dumps({
            'data': self.data,
            'format': self.format_type
        }, indent=2)

class ShellAdapter:
    """
    Simplified shell adapter to handle Bash commands only.
    NuShell references have been removed as requested.
    """
    def __init__(self, test_mode: bool = False, working_dir: Path = None):
        self.test_mode = test_mode
        self.working_dir = working_dir or Path.cwd()
        self.command_history = []

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """
        Execute a bash command, returning (stdout, stderr, exit_code).
        If test_mode is True, no command is actually executed.
        """
        if self.test_mode:
            msg = f"[TEST MODE] Command NOT executed: {command}"
            logger.info(msg)
            return (msg, "", 0)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            stdout, stderr = await process.communicate()
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""
            code = process.returncode
            return (stdout_str, stderr_str, code)
        except Exception as e:
            err = f"Error executing command: {str(e)}"
            logger.error(err)
            return ("", err, 1)

    def get_command_history(self):
        return self.command_history

    def clear_history(self):
        self.command_history = []
