import asyncio
import re
from typing import Dict, List, Pattern, Optional, Union, Tuple
from dataclasses import dataclass
import pty
import os
import termios
import struct
import fcntl
import logging

logger = logging.getLogger(__name__)

@dataclass
class InteractionPattern:
    """Defines an expected interaction pattern"""
    pattern: Union[str, Pattern]
    response: str
    timeout: float = 5.0
    required: bool = False

class InteractiveCommandHandler:
    """Handles interactive command execution with pattern matching"""
    
    DEFAULT_PATTERNS = {
        'yes_no': InteractionPattern(
            pattern=re.compile(r'\[Y/n\]|\[y/N\]|\(Y/n\)|\(y/N\)', re.IGNORECASE),
            response='y\n',
            timeout=5.0
        ),
        'password': InteractionPattern(
            pattern=re.compile(r'password:|passphrase:', re.IGNORECASE),
            response='\n',  # Default empty password, should be overridden
            timeout=10.0
        ),
        'continue': InteractionPattern(
            pattern=re.compile(r'press.*continue|continue\?|proceed\?', re.IGNORECASE),
            response='\n',
            timeout=5.0
        ),
        'sudo': InteractionPattern(
            pattern=re.compile(r'\[sudo\] password'),
            response=f'{os.getenv("SUDO_PASSWORD", "")}\n',
            timeout=15.0
        ),
        'ssh_confirm': InteractionPattern(
            pattern=re.compile(r'Are you sure you want to continue connecting'),
            response='yes\n',
            timeout=10.0
        )
    }

    def __init__(self):
        self.patterns = self.DEFAULT_PATTERNS.copy()
        self.master_fd = None
        self.slave_fd = None

    def add_pattern(self, name: str, pattern: InteractionPattern):
        """Add a new interaction pattern"""
        self.patterns[name] = pattern

    def _create_pty(self) -> Tuple[int, int]:
        """Create a new PTY pair"""
        return pty.openpty()

    async def _read_output(self, fd: int, timeout: float = 0.1) -> Optional[str]:
        """Read output from PTY with timeout"""
        try:
            output = ""
            while True:
                try:
                    chunk = os.read(fd, 1024).decode()
                    if not chunk:
                        break
                    output += chunk
                except (OSError, IOError):
                    break
            return output
        except Exception as e:
            logger.error(f"Error reading from PTY: {e}")
            return None

    async def _write_input(self, fd: int, data: str):
        """Write input to PTY"""
        try:
            os.write(fd, data.encode())
        except Exception as e:
            logger.error(f"Error writing to PTY: {e}")

    async def _handle_interaction(self, output: str) -> Optional[str]:
        """Check output against patterns and return appropriate response"""
        for name, pattern in self.patterns.items():
            if isinstance(pattern.pattern, str):
                if pattern.pattern in output:
                    return pattern.response
            else:  # regex pattern
                if pattern.pattern.search(output):
                    return pattern.response
        return None

    async def run_interactive_command(self, command: str, 
                                    custom_patterns: Dict[str, InteractionPattern] = None,
                                    timeout: float = 30.0) -> Tuple[str, str, int]:
        """Run an interactive command with pattern matching"""
        if custom_patterns:
            self.patterns.update(custom_patterns)

        try:
            # Create PTY
            master_fd, slave_fd = self._create_pty()
            self.master_fd, self.slave_fd = master_fd, slave_fd

            # Start process
            process = await asyncio.create_subprocess_shell(
                command,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True
            )

            output = ""
            start_time = asyncio.get_event_loop().time()

            while True:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    break

                # Read output
                new_output = await self._read_output(master_fd)
                if new_output:
                    output += new_output
                    
                    # Check for interaction patterns
                    response = await self._handle_interaction(output)
                    if response:
                        await self._write_input(master_fd, response)

                # Check if process has finished
                try:
                    returncode = process.returncode
                    if returncode is not None:
                        break
                except ProcessLookupError:
                    break

                await asyncio.sleep(0.1)

            # Clean up
            try:
                process.terminate()
            except ProcessLookupError:
                pass

            os.close(master_fd)
            os.close(slave_fd)

            return output, "", process.returncode if process.returncode else 0

        except Exception as e:
            logger.error(f"Interactive command failed: {e}")
            return "", str(e), 1
