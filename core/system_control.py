import asyncio
import logging
from typing import Tuple, Optional
from pathlib import Path
from .memory_manager import MemoryManager
from .shell_adapter import ShellAdapter

logger = logging.getLogger(__name__)

UNSAFE_COMMANDS = {
    "rm -rf /": "FULL_SYSTEM_WIPE",
    "chmod 777": "INSECURE_PERMISSIONS"
}

class SystemControl:
    """Enhanced system control with support for single (bash) command type and test mode"""
    
    def __init__(self, preferred_shell: str = 'bash', test_mode: bool = False):
        self.memory_manager = MemoryManager()
        self.working_dir = Path.cwd()
        self.preferred_shell = preferred_shell
        self.test_mode = test_mode
        self.bash_adapter = ShellAdapter(test_mode=self.test_mode, working_dir=self.working_dir)

    def _sanitize_command(self, command: str) -> str:
        for pattern, danger_type in UNSAFE_COMMANDS.items():
            if pattern in command:
                logger.warning(f"DANGER: Attempted {danger_type} command => {command}")
                self.memory_manager.save_document(
                    "security_warnings",
                    f"⚠️ DANGER: {danger_type} attempt: {command}"
                )
        return command

    async def execute_command(self, command_type: str, command: str) -> Tuple[str, str, int]:
        """
        Currently ignoring command_type (since everything is just bash now).
        If test_mode is True, no real commands are run.
        """
        command = self._sanitize_command(command)
        logger.info(f"Executing command (test_mode={self.test_mode}): {command}")
        return await self.bash_adapter.execute(command)

    def cleanup(self):
        self.bash_adapter.clear_history()
