import asyncio
import logging
import shlex
from typing import Tuple, Optional, Dict, List
from pathlib import Path
from datetime import datetime
from .interactive_handler import InteractiveCommandHandler, InteractionPattern

logger = logging.getLogger(__name__)

class SystemControl:
    """Enhanced system control with interactive command support"""
    
    # Commands that typically require interaction
    INTERACTIVE_COMMANDS = {
        'pacman': ['-S', '-Syu'],
        'apt': ['install', 'upgrade'],
        'apt-get': ['install', 'upgrade'],
        'pip': ['install'],
        'npm': ['install'],
        'docker': ['run', 'exec'],
        'ssh': [],  # Empty list means the command itself is interactive
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
        self.user = user
        self.working_dir = working_dir or Path.cwd()
        self.process_map = {}  # Track long-running processes
        self.interactive_handler = InteractiveCommandHandler()
        
    def _sanitize_command(self, command: str) -> str:
        """Basic command sanitization"""
        return command.replace('\0', '')

    def _is_interactive_command(self, command: str) -> bool:
        """Determine if a command typically requires interaction"""
        try:
            args = shlex.split(command)
            if not args:
                return False
                
            base_cmd = args[0].split('/')[-1]  # Handle path-based commands
            
            if base_cmd in self.INTERACTIVE_COMMANDS:
                if not self.INTERACTIVE_COMMANDS[base_cmd]:  # Empty list means always interactive
                    return True
                    
                # Check if any of the command's arguments match the interactive flags
                return any(flag in args[1:] for flag in self.INTERACTIVE_COMMANDS[base_cmd])
                
            return False
            
        except Exception as e:
            logger.error(f"Error checking interactive command: {e}")
            return False

    def _get_custom_patterns(self, command: str) -> Dict[str, InteractionPattern]:
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
        elif base_cmd == 'pip':
            patterns['proceed'] = InteractionPattern(
                pattern=r'Proceed \([y/N]\)',
                response='y\n'
            )
        elif base_cmd == 'npm':
            patterns['proceed'] = InteractionPattern(
                pattern=r'Ok to proceed\? \(y\)',
                response='y\n'
            )
        
        return patterns

    async def execute_command(self, command: str) -> Tuple[str, str, int]:
        """Execute a command with automatic interactive support"""
        command = self._sanitize_command(command)
        logger.info(f"Executing command: {command}")
        
        try:
            # Check if command needs interactive handling
            if self._is_interactive_command(command):
                logger.info(f"Using interactive handler for command: {command}")
                custom_patterns = self._get_custom_patterns(command)
                
                stdout, stderr, code = await self.interactive_handler.run_interactive_command(
                    command,
                    custom_patterns=custom_patterns
                )
                
                if code == 0:
                    logger.info("Interactive command completed successfully")
                else:
                    logger.warning(f"Interactive command failed with exit code: {code}")
                
                return stdout, stderr, code
            
            # Non-interactive command execution
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            
            stdout, stderr = await process.communicate()
            
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""
            
            if process.returncode == 0:
                logger.info("Command completed successfully")
            else:
                logger.warning(f"Command failed with exit code: {process.returncode}")
                if stderr_str:
                    logger.warning(f"Error output: {stderr_str}")
            
            return stdout_str, stderr_str, process.returncode
            
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return "", error_msg, 1

    async def start_process(self, command: str) -> Optional[Dict]:
        """Start a long-running process"""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            
            process_info = {
                'process': process,
                'command': command,
                'start_time': datetime.now(),
                'stdout': [],
                'stderr': []
            }
            
            self.process_map[id(process)] = process_info
            return process_info
            
        except Exception as e:
            logger.error(f"Error starting process: {str(e)}")
            return None

    async def check_process(self, process_id: int) -> Optional[Dict]:
        """Check status of a running process"""
        process_info = self.process_map.get(process_id)
        if not process_info:
            return None
            
        process = process_info['process']
        
        if process.returncode is not None:
            # Process has finished
            stdout, stderr = await process.communicate()
            return {
                'command': process_info['command'],
                'returncode': process.returncode,
                'stdout': stdout.decode() if stdout else "",
                'stderr': stderr.decode() if stderr else "",
                'runtime': datetime.now() - process_info['start_time']
            }
            
        return {
            'command': process_info['command'],
            'running': True,
            'runtime': datetime.now() - process_info['start_time']
        }

    def cleanup(self):
        """Cleanup any running processes"""
        for process_info in self.process_map.values():
            try:
                process_info['process'].terminate()
            except:
                pass
        self.process_map.clear()
