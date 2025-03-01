import asyncio
import logging
from typing import Tuple
from pathlib import Path
import json
from dataclasses import dataclass
import pexpect
import sys
import time

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
    Simplified shell adapter to handle Bash commands only, with
    optional interactive support via pexpect.
    """
    def __init__(self, test_mode: bool = False, working_dir: Path = None):
        self.test_mode = test_mode
        self.working_dir = working_dir or Path.cwd()
        self.command_history = []

    async def execute(self, command: str, timeout: int = 120) -> Tuple[str, str, int]:
        """
        Execute a bash command, returning (stdout, stderr, exit_code).
        If test_mode is True, no command is actually executed.
        
        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds (default: 120 seconds)
            
        Returns:
            Tuple of (stdout, stderr, exit_code)
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
            
            # Use asyncio.wait_for to implement the timeout
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                stdout_str = stdout.decode() if stdout else ""
                stderr_str = stderr.decode() if stderr else ""
                code = process.returncode
            except asyncio.TimeoutError:
                # If we timeout, attempt to kill the process
                try:
                    process.kill()
                    await process.wait()
                except Exception as kill_error:
                    logger.error(f"Error killing process after timeout: {kill_error}")
                    
                logger.warning(f"Command timed out after {timeout} seconds: {command[:100]}...")
                return ("", f"ERROR: Command timed out after {timeout} seconds", 1)
                
            # Record in command history
            self.command_history.append({
                'command': command,
                'exit_code': code,
                'timestamp': time.time()
            })
                
            return (stdout_str, stderr_str, code)
        except Exception as e:
            err = f"Error executing command: {str(e)}"
            logger.error(err)
            return ("", err, 1)

    async def execute_interactive(self, command: str, timeout: int = 180) -> Tuple[str, str, int]:
        """
        Execute an interactive bash command with pexpect.
        We'll watch for typical `[Y/n]` or `[y/N]` prompts and auto-send 'y'.
        This is naive: real usage would parse more prompts and handle them more thoroughly.
        
        Args:
            command: The command to execute interactively
            timeout: Maximum execution time in seconds (default: 180 seconds)
            
        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        if self.test_mode:
            msg = f"[TEST MODE] Interactive Command NOT executed: {command}"
            logger.info(msg)
            return (msg, "", 0)

        # Because we are in an async environment, we can spawn pexpect in a thread
        # or we can do the simpler approach of just running pexpect in a blocking way.
        # We'll do a thread approach for simplicity. pexpect is inherently blocking in nature.
        loop = asyncio.get_event_loop()
        
        # Implement timeout for the executor task
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self._run_pexpect_blocking, command, timeout),
                timeout=timeout + 30  # Give a bit extra time for the executor itself
            )
            return result
        except asyncio.TimeoutError:
            logger.warning(f"Interactive command timed out after {timeout} seconds: {command[:100]}...")
            return ("", f"ERROR: Interactive command timed out after {timeout} seconds", 1)

    def _run_pexpect_blocking(self, command: str, timeout: int = 180) -> Tuple[str, str, int]:
        """Blocking call to pexpect, capturing output."""
        start_time = time.time()
        output_buffer = []
        
        try:
            # Start a shell with pexpect
            child = pexpect.spawn(
                "/bin/bash",
                ["-c", command],
                cwd=str(self.working_dir),
                encoding='utf-8',
                echo=False,
                timeout=min(30, timeout)  # Use the smaller value for pexpect's internal timeout
            )
            child.logfile_read = sys.stdout

            # We'll do a loop that checks for a few known patterns
            while True:
                # Check if we've exceeded our timeout
                if time.time() - start_time > timeout:
                    logger.warning(f"Pexpect command exceeded timeout: {command[:100]}...")
                    try:
                        child.sendintr()  # Try to send Ctrl+C first
                        child.terminate(force=True)
                    except:
                        pass
                    return ("\n".join(output_buffer), f"ERROR: Command exceeded timeout of {timeout}s", 1)
                
                try:
                    index = child.expect([
                        r'\[Y/n\]',         # typical yes/no
                        r'\[y/N\]', 
                        r'(y/n)',           # Another common prompt format
                        r'(Y/n)',
                        r'(y/N)',
                        r'Do you want to continue',
                        r'password',        # Password prompt
                        r'continue\?',      # Continue prompt
                        pexpect.EOF,        # end of process
                        pexpect.TIMEOUT
                    ], timeout=30)
                    
                    # Capture output
                    if child.before:
                        output_buffer.append(child.before)
                    
                    if index in (0, 1, 2, 3, 4, 5, 7):
                        # We see a yes/no prompt. We'll send 'y\n'
                        child.sendline("y")
                    elif index == 6:  # Password prompt - abort for security
                        logger.warning("Password prompt detected, aborting command for security")
                        child.terminate(force=True)
                        return ("\n".join(output_buffer), "ERROR: Password prompt detected, command aborted", 1)
                    elif index == 8:  # EOF
                        break
                    elif index == 9:  # TIMEOUT
                        # Continue but log it
                        logger.debug(f"Pexpect timeout during command execution (continuing): {command[:100]}...")
                except pexpect.EOF:
                    break
                except pexpect.TIMEOUT:
                    # Continue on timeout (just a single expect timeout, not overall timeout)
                    logger.debug(f"Pexpect timeout during command execution (continuing): {command[:100]}...")

            # Add a timeout for wait so it doesn't hang
            wait_result = child.wait(timeout=30)
            exit_code = child.exitstatus if child.exitstatus is not None else 0
            
            # Collect what's left in the buffer
            remainder = child.read() if not child.closed else ""
            if remainder:
                output_buffer.append(remainder)
                
            # Record in command history
            self.command_history.append({
                'command': command,
                'exit_code': exit_code,
                'timestamp': time.time(),
                'interactive': True,
                'duration': time.time() - start_time
            })
                
            child.close()
            return ("\n".join(output_buffer), "", exit_code)
        except Exception as e:
            err = f"Error in interactive command: {str(e)}"
            logger.error(err)
            return ("\n".join(output_buffer) if output_buffer else "", err, 1)

    def get_command_history(self):
        return self.command_history

    def clear_history(self):
        self.command_history = []
