import asyncio
import os
import sys
import subprocess
import logging
from typing import Tuple, Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

class ShellAdapter:
    """
    Manages interactions with the system shell.
    Executes commands in a controlled environment and provides security checks.
    """

    def __init__(self, working_directory: str = None, environment: Dict[str, str] = None):
        self.working_directory = working_directory or os.getcwd()
        self.environment = environment or dict(os.environ)
        self.shell_type = "bash" if sys.platform != "win32" else "cmd"
        self.interactive_shell = None
        self.interactive_process = None
        self.home_directory = str(Path.home())

    async def execute_command(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        """
        Execute a command in the system shell and return the stdout, stderr, and return code.

        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds

        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        try:
            # Handle tilde expansion in paths
            if "~" in command:
                command = command.replace("~", self.home_directory)

            logger.info(f"Executing command: {command}")

            # Security checks
            if self._is_dangerous_command(command):
                return "", "Command rejected due to security concerns", 1

            # Execute the command with timeout
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                env=self.environment,
                shell=True
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                stdout = stdout_bytes.decode('utf-8', errors='replace')
                stderr = stderr_bytes.decode('utf-8', errors='replace')
                return_code = process.returncode

                logger.debug(f"Command completed with code {return_code}")
                return stdout, stderr, return_code
            except asyncio.TimeoutError:
                # Try to terminate the process if it's still running
                try:
                    process.terminate()
                    await asyncio.sleep(0.5)
                    if process.returncode is None:
                        process.kill()
                except:
                    pass

                logger.warning(f"Command timed out after {timeout} seconds: {command}")
                return "", f"Command execution timed out after {timeout} seconds", 124

        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return "", f"Error executing command: {str(e)}", 1

    def _is_dangerous_command(self, command: str) -> bool:
        """
        Check if the command contains potentially dangerous operations.

        Args:
            command: The command to check

        Returns:
            True if the command is potentially dangerous, False otherwise
        """
        # Blacklist of dangerous commands
        dangerous_patterns = [
            "rm -rf /",
            ":(){ :|:& };:",
            "> /dev/sda",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs",
            "wget -O- http",
            "curl -s http",
            "> /dev/null",
        ]

        command_lower = command.lower()
        for pattern in dangerous_patterns:
            if pattern in command_lower:
                logger.warning(f"Blocked potentially dangerous command: {command}")
                return True

        return False

    async def start_interactive_shell(self) -> bool:
        """
        Start an interactive shell that persists between commands.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.interactive_process = await asyncio.create_subprocess_shell(
                self.shell_type,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                env=self.environment
            )
            return True
        except Exception as e:
            logger.error(f"Error starting interactive shell: {e}")
            return False

    async def execute_in_interactive_shell(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        """
        Execute a command in the interactive shell.

        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds

        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        if not self.interactive_process:
            if not await self.start_interactive_shell():
                return "", "Failed to start interactive shell", 1

        try:
            # Send command to the shell
            self.interactive_process.stdin.write(f"{command}\n".encode('utf-8'))
            await self.interactive_process.stdin.drain()

            # Add a special marker to know when the command has completed
            marker = f"__CMD_COMPLETE_{os.urandom(4).hex()}__"
            self.interactive_process.stdin.write(f"echo {marker} $?\n".encode('utf-8'))
            await self.interactive_process.stdin.drain()

            # Read output until we find the marker
            stdout_chunks = []
            stderr_chunks = []
            return_code = 0

            async def read_until_marker():
                buffer = b""
                while True:
                    chunk = await asyncio.wait_for(self.interactive_process.stdout.read(1024), timeout=1)
                    if not chunk:
                        break
                    buffer += chunk
                    if marker.encode('utf-8') in buffer:
                        break
                return buffer.decode('utf-8', errors='replace')

            try:
                output = await asyncio.wait_for(read_until_marker(), timeout=timeout)
                stdout_chunks.append(output)

                # Extract return code
                if marker in output:
                    parts = output.split(marker)
                    if len(parts) > 1 and parts[1].strip():
                        try:
                            return_code = int(parts[1].strip())
                        except:
                            pass
                    output = parts[0]

                return output, "", return_code
            except asyncio.TimeoutError:
                return "".join(stdout_chunks), "Command execution timed out", 124

        except Exception as e:
            logger.error(f"Error executing command in interactive shell: {e}")
            return "", f"Error: {str(e)}", 1

    def close_interactive_shell(self):
        """
        Close the interactive shell if it's open.
        """
        if self.interactive_process:
            try:
                self.interactive_process.terminate()
                self.interactive_process = None
            except Exception as e:
                logger.error(f"Error closing interactive shell: {e}")

    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get information about the current environment.

        Returns:
            Dictionary with environment information
        """
        info = {
            "shell_type": self.shell_type,
            "working_directory": self.working_directory,
            "hostname": os.environ.get("HOSTNAME", ""),
            "username": os.environ.get("USER", ""),
            "platform": sys.platform,
            "python_version": sys.version,
            "interactive_mode": self.interactive_process is not None
        }

        # Try to get more system info
        try:
            import platform
            info["os"] = platform.system()
            info["os_release"] = platform.release()
            info["os_version"] = platform.version()
            info["machine"] = platform.machine()
            info["processor"] = platform.processor()
        except:
            pass

        return info