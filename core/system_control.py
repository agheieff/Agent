import asyncio
import logging
import shlex
import sys
from typing import Tuple, Optional, Dict, List, Union
from pathlib import Path
from datetime import datetime
from .memory_manager import MemoryManager
from .shell_adapter import ShellAdapter

UNSAFE_COMMANDS = {
    "rm -rf /": "FULL_SYSTEM_WIPE",
    "chmod 777": "INSECURE_PERMISSIONS"
}

logger = logging.getLogger(__name__)

class CommandExecutor:
    """Base class for command execution"""
    async def execute(self, command: str) -> Tuple[str, str, int]:
        raise NotImplementedError

class BashExecutor(CommandExecutor):
    """Handles bash command execution"""
    def __init__(self, working_dir: Optional[Path] = None):
        self.working_dir = working_dir or Path.cwd()
        self.shell_adapter = ShellAdapter(preferred_shell='bash')

    async def execute(self, command: str) -> Tuple[str, str, int]:
        try:
            return await self.shell_adapter.execute(command)
        except Exception as e:
            error_msg = f"Error executing bash command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

class NuShellExecutor(CommandExecutor):
    """Handles Nu shell command execution"""
    def __init__(self, working_dir: Optional[Path] = None):
        self.working_dir = working_dir or Path.cwd()
        self.shell_adapter = ShellAdapter(preferred_shell='nu')

    async def execute(self, command: str) -> Tuple[str, str, int]:
        try:
            return await self.shell_adapter.execute(command)
        except Exception as e:
            error_msg = f"Error executing nu shell command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

class SystemControl:
    """Enhanced system control with support for multiple command types"""
    
    def __init__(self, preferred_shell: str = 'nu'):
        self.memory_manager = MemoryManager()
        self.working_dir = Path.cwd()
        self.preferred_shell = preferred_shell
        
        # Initialize executors
        self.executors = {
            'bash': BashExecutor(self.working_dir),
            'nu': NuShellExecutor(self.working_dir)
        }

    def _sanitize_command(self, command: str) -> str:
        """Log warnings instead of blocking"""
        for pattern, danger_type in UNSAFE_COMMANDS.items():
            if pattern in command:
                logger.warning(f"DANGER: Attempted {danger_type} command")
                self.memory_manager.save_document(
                    "security_warnings",
                    f"⚠️ {datetime.now()}: {danger_type} attempt: {command}"
                )
        return command

    async def execute_command(self, command_type: str, command: str) -> Tuple[str, str, int]:
        """Execute a command of the specified type"""
        # Default to preferred shell for shell commands
        if command_type.lower() in ['bash', 'shell', 'nu']:
            command_type = self.preferred_shell
            
        executor = self.executors.get(command_type.lower())
        if not executor:
            return "", f"Unsupported command type: {command_type}", 1
            
        command = self._sanitize_command(command)
        logger.info(f"Executing {command_type} command: {command}")
        
        try:
            stdout, stderr, code = await executor.execute(command)
            
            if code == 0:
                logger.info(f"{command_type} command completed successfully")
            else:
                logger.warning(f"{command_type} command failed with exit code: {code}")
                if stderr:
                    logger.warning(f"Error output: {stderr}")
            
            return stdout, stderr, code
            
        except Exception as e:
            error_msg = f"Error executing {command_type} command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

    def cleanup(self):
        """Cleanup resources"""
        # Add cleanup for shell adapters
        for executor in self.executors.values():
            if hasattr(executor, 'shell_adapter'):
                executor.shell_adapter.clear_history()
