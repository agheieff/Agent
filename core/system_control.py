import asyncio
import logging
import shlex
import sys
from typing import Tuple, Optional, Dict, List, Union
from pathlib import Path
from datetime import datetime
from .interactive_handler import InteractiveCommandHandler, InteractionPattern
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
    def __init__(self, interactive_handler: InteractiveCommandHandler, working_dir: Optional[Path] = None):
        self.interactive_handler = interactive_handler
        self.working_dir = working_dir or Path.cwd()
        self.shell_adapter = ShellAdapter(preferred_shell='bash')

    async def execute(self, command: str) -> Tuple[str, str, int]:
        try:
            # Use interactive handler for interactive commands
            if SystemControl._is_interactive_command(command):
                custom_patterns = SystemControl._get_custom_patterns(command)
                return await self.interactive_handler.run_interactive_command(
                    command,
                    custom_patterns=custom_patterns
                )

            # Use shell adapter for command execution
            return await self.shell_adapter.execute(command)

        except Exception as e:
            error_msg = f"Error executing bash command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

class PythonExecutor(CommandExecutor):
    def __init__(self):
        self.process = None
        
    async def execute(self, code: str) -> Tuple[str, str, int]:
        try:
            if not self.process or self.process.returncode is not None:
                self.process = await asyncio.create_subprocess_shell(
                    "python -iq -u",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env={**os.environ, "PYTHONSTARTUP": ""}
                )

            self.process.stdin.write(f"{code}\n".encode())
            await self.process.stdin.drain()
            
            # Get output with timeout
            stdout, stderr = await asyncio.wait_for(
                self.process.communicate(),
                timeout=15
            )
            return stdout.decode(), stderr.decode(), self.process.returncode
        except Exception as e:
            return "", str(e), 1

class NuShellExecutor(CommandExecutor):
    """Handles Nu shell command execution"""
    def __init__(self, interactive_handler: InteractiveCommandHandler, working_dir: Optional[Path] = None):
        self.interactive_handler = interactive_handler
        self.working_dir = working_dir or Path.cwd()
        self.shell_adapter = ShellAdapter(preferred_shell='nu')

    async def execute(self, command: str) -> Tuple[str, str, int]:
        try:
            # Use interactive handler for interactive commands
            if SystemControl._is_interactive_command(command):
                custom_patterns = SystemControl._get_custom_patterns(command)
                return await self.interactive_handler.run_interactive_command(
                    command,
                    custom_patterns=custom_patterns
                )

            # Use shell adapter for command execution
            return await self.shell_adapter.execute(command)

        except Exception as e:
            error_msg = f"Error executing nu shell command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

class SystemControl:
    """Enhanced system control with support for multiple command types"""
    
    # Interactive command patterns
    INTERACTIVE_COMMANDS = {
        'pacman': ['-S', '-Syu'],
        'apt': ['install', 'upgrade'],
        'apt-get': ['install', 'upgrade'],
        'pip': ['install'],
        'npm': ['install'],
        'docker': ['run', 'exec'],
        'ssh': [],
        'mysql': [],
        'psql': [],
        'nano': [],
        'vim': [],
        'top': [],
        'htop': [],
        'less': [],
        'more': []
    }

    def __init__(self, user: str = None, working_dir: Optional[Path] = None, preferred_shell: str = 'nu'):
        self.memory_manager = MemoryManager()
        self.working_dir = working_dir or Path.cwd()
        self.interactive_handler = InteractiveCommandHandler()
        self.preferred_shell = preferred_shell
        
        # Initialize executors
        self.executors = {
            'bash': BashExecutor(self.interactive_handler, self.working_dir),
            'python': PythonExecutor(),
            'nu': NuShellExecutor(self.interactive_handler, self.working_dir)
        }

    @staticmethod
    def _is_interactive_command(command: str) -> bool:
        """Determine if a command typically requires interaction"""
        try:
            args = shlex.split(command)
            if not args:
                return False
                
            base_cmd = args[0].split('/')[-1]
            
            if base_cmd in SystemControl.INTERACTIVE_COMMANDS:
                if not SystemControl.INTERACTIVE_COMMANDS[base_cmd]:
                    return True
                return any(flag in args[1:] for flag in SystemControl.INTERACTIVE_COMMANDS[base_cmd])
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking interactive command: {e}")
            return False

    @staticmethod
    def _get_custom_patterns(command: str) -> Dict[str, InteractionPattern]:
        """Get custom interaction patterns for specific commands"""
        args = shlex.split(command)
        base_cmd = args[0].split('/')[-1]
        
        patterns = {}
        
        if base_cmd == 'pacman':
            patterns.update({
                'proceed': InteractionPattern(
                    pattern=r'Proceed with installation\?',
                    response='y\n'
                ),
                'trust': InteractionPattern(
                    pattern=r'Trust this package\?',
                    response='y\n'
                )
            })
        elif base_cmd in ['apt', 'apt-get']:
            patterns.update({
                'continue': InteractionPattern(
                    pattern=r'Do you want to continue\?',
                    response='y\n'
                ),
                'restart': InteractionPattern(
                    pattern=r'Restart services during package upgrades',
                    response='y\n'
                )
            })
        
        return patterns

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
