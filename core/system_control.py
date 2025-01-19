import asyncio
import logging
import shlex
import sys
from typing import Tuple, Optional, Dict, List, Union
from pathlib import Path
from datetime import datetime
from .interactive_handler import InteractiveCommandHandler, InteractionPattern

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

    async def execute(self, command: str) -> Tuple[str, str, int]:
        try:
            # Use interactive handler for interactive commands
            if SystemControl._is_interactive_command(command):
                custom_patterns = SystemControl._get_custom_patterns(command)
                return await self.interactive_handler.run_interactive_command(
                    command,
                    custom_patterns=custom_patterns
                )

            # Standard command execution
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            
            stdout, stderr = await process.communicate()
            return stdout.decode() if stdout else "", stderr.decode() if stderr else "", process.returncode

        except Exception as e:
            error_msg = f"Error executing bash command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

class PythonExecutor(CommandExecutor):
    """Handles Python code execution"""
    def __init__(self):
        self.locals = {}
        self.globals = {'__builtins__': __builtins__}

    async def execute(self, code: str) -> Tuple[str, str, int]:
        import io
        import contextlib
        
        stdout = io.StringIO()
        stderr = io.StringIO()
        
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(code, self.globals, self.locals)
            return stdout.getvalue(), stderr.getvalue(), 0
        except Exception as e:
            return stdout.getvalue(), f"{str(e)}\n{stderr.getvalue()}", 1

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

    def __init__(self, user: str = None, working_dir: Optional[Path] = None):
        self.working_dir = working_dir or Path.cwd()
        self.interactive_handler = InteractiveCommandHandler()
        
        # Initialize executors
        self.executors = {
            'bash': BashExecutor(self.interactive_handler, self.working_dir),
            'python': PythonExecutor(),
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
        """Basic command sanitization"""
        return command.replace('\0', '')

    async def execute_command(self, command_type: str, command: str) -> Tuple[str, str, int]:
        """Execute a command of the specified type"""
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
        # Add any cleanup logic here
        pass
