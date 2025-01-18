import asyncio
import logging
import shlex
from typing import Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class SystemControl:
    def __init__(self, user: str = None, working_dir: Optional[Path] = None):
        self.user = user
        self.working_dir = working_dir or Path.cwd()
        self.process_map = {}  # Track long-running processes
        
    def _sanitize_command(self, command: str) -> str:
        """Basic command sanitization"""
        # Remove any null bytes or other dangerous characters
        return command.replace('\0', '')

    async def execute_command(self, command: str) -> Tuple[str, str, int]:
        """Execute a shell command with proper sanitization and logging"""
        command = self._sanitize_command(command)
        logger.info(f"Executing command: {command}")
        
        try:
            # Use shlex to properly handle command arguments
            args = shlex.split(command)
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            
            logger.debug("Process created, awaiting completion...")
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

    async def execute_interactive(self, command: str) -> Optional[asyncio.subprocess.Process]:
        """Start an interactive process with better error handling"""
        command = self._sanitize_command(command)
        logger.info(f"Starting interactive process: {command}")
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            
            # Store process reference
            process_id = id(process)
            self.process_map[process_id] = {
                'process': process,
                'command': command,
                'start_time': datetime.now()
            }
            
            return process
            
        except Exception as e:
            logger.error(f"Error starting interactive process: {str(e)}", exc_info=True)
            return None
