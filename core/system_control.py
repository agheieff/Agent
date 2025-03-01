import asyncio
import logging
import time
import os
from typing import Tuple, Optional, Dict, List, Any
from pathlib import Path

from .memory_manager import MemoryManager
from .shell_adapter import ShellAdapter
from .file_operations import FileOperations

logger = logging.getLogger(__name__)

UNSAFE_COMMANDS = {
    # System-breaking commands
    "rm -rf /": "FULL_SYSTEM_WIPE",
    "rm -rf /*": "FULL_SYSTEM_WIPE",
    "rm -rf --no-preserve-root /": "FULL_SYSTEM_WIPE",
    ":(){ :|:& };:": "FORK_BOMB",
    "dd if=/dev/random of=/dev/sda": "DISK_DESTRUCTION",
    
    # Security risks
    "chmod 777": "INSECURE_PERMISSIONS",
    "chmod -R 777": "INSECURE_PERMISSIONS",
    "chown -R nobody:nogroup /": "OWNERSHIP_CHANGE",
    
    # Suspicious network activity
    "nc -e": "REVERSE_SHELL",
    "bash -i >& /dev/tcp/": "REVERSE_SHELL",
    "wget http": "SUSPICIOUS_DOWNLOAD",
    "curl http": "SUSPICIOUS_DOWNLOAD"
}

class SecurityWarning(Exception):
    """Exception raised for security concerns in commands"""
    pass

class SystemControl:
    """Enhanced system control with support for command execution, tracking, file operations, and self-monitoring"""
    
    def __init__(self, preferred_shell: str = 'bash', test_mode: bool = False):
        self.memory_manager = MemoryManager()
        self.working_dir = Path.cwd()
        self.preferred_shell = preferred_shell
        self.test_mode = test_mode
        self.bash_adapter = ShellAdapter(test_mode=self.test_mode, working_dir=self.working_dir)
        self.file_ops = FileOperations()
        self.command_history: List[Dict] = []
        self.resource_limits = {
            'max_execution_time': 120,      # 2 minutes max execution time for most commands
            'max_output_size': 1024 * 1024, # 1MB max output
            'max_temp_files': 100,          # Max temp files
            'interactive_timeout': 180      # 3 minutes for interactive commands
        }
        self.stats = {
            'commands_executed': 0,
            'file_operations': 0,
            'errors': 0,
            'total_execution_time': 0,
            'last_execution_time': 0,
            'timeout_commands': 0
        }

    def _sanitize_command(self, command: str) -> str:
        """
        UNRESTRICTED - No command sanitization or safety checks.
        
        Returns the original command without safety checks.
        """
        command = command.strip()
        
        # No safety restrictions - log command for reference but allow everything
        for pattern, danger_type in UNSAFE_COMMANDS.items():
            if pattern in command:
                logger.warning(f"EXECUTING POTENTIALLY DANGEROUS COMMAND: {danger_type} => {command}")
                self.memory_manager.save_document(
                    "command_execution",
                    f"EXECUTING: {danger_type} command: {command}",
                    tags=["command", "execution", danger_type]
                )
                # Continue execution without raising exception
                
        # Allow self-modification
        agent_path_patterns = [
            "core/agent.py", 
            "core/memory_manager.py",
            "core/system_control.py",
            "run_agent.py"
        ]
        for path in agent_path_patterns:
            if path in command and any(edit_cmd in command.lower() for edit_cmd in ["rm ", "mv ", "edit", ">", "cp "]):
                logger.warning(f"EXECUTING AGENT SELF-MODIFICATION: {command}")
                self.memory_manager.save_document(
                    "command_execution",
                    f"EXECUTING AGENT SELF-MODIFICATION: {command}",
                    tags=["command", "execution", "self_modification"]
                )
                # Continue execution without raising exception
                
        return command

    async def execute_command(self, command_type: str, command: str, interactive: bool = False, 
                               timeout: int = None) -> Tuple[str, str, int]:
        """
        Execute a command after sanitization with timeout enforcement.
        
        Args:
            command_type: Type of command ('bash' or 'python')
            command: The command to execute
            interactive: Whether to use interactive mode
            timeout: Maximum execution time in seconds, uses resource_limits if not specified
            
        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        try:
            # Use specified timeout or default from resource limits
            if timeout is None:
                timeout = self.resource_limits['max_execution_time']
            
            # Sanitize command (will raise SecurityWarning if unsafe)
            sanitized_cmd = self._sanitize_command(command)
            logger.info(f"Executing command (test_mode={self.test_mode}, interactive={interactive}, timeout={timeout}s): {sanitized_cmd}")
            
            # Track command start time
            start_time = time.time()
            
            # Record command in history
            cmd_record = {
                'command': sanitized_cmd,
                'type': command_type,
                'start_time': start_time,
                'interactive': interactive,
                'timeout': timeout
            }
            self.command_history.append(cmd_record)
            
            # Determine execution method based on command type
            if command_type == 'python':
                # For Python commands, create a temporary file and execute it
                content = sanitized_cmd
                tmp_dir = Path("memory/temp")
                tmp_dir.mkdir(exist_ok=True)
                
                # Create a unique filename
                filename = f"exec_{int(time.time())}_{hash(content) % 10000}.py"
                tmp_file = tmp_dir / filename
                
                # Check if we have too many temp files
                temp_files = list(tmp_dir.glob("exec_*.py"))
                if len(temp_files) > self.resource_limits['max_temp_files']:
                    # Clean up old files
                    temp_files.sort(key=lambda f: f.stat().st_mtime)
                    for old_file in temp_files[:-self.resource_limits['max_temp_files']]:
                        try:
                            old_file.unlink()
                        except:
                            pass
                
                with open(tmp_file, 'w') as f:
                    f.write(content)
                
                # Execute the Python file
                actual_cmd = f"python {tmp_file}"
                if interactive:
                    result = await self.bash_adapter.execute_interactive(actual_cmd, timeout=timeout)
                else:
                    result = await self.bash_adapter.execute(actual_cmd, timeout=timeout)
                
                # Keep the file for debugging, but log its location
                logger.info(f"Python script saved at {tmp_file}")
                
            else:  # Assume bash/shell
                if interactive:
                    result = await self.bash_adapter.execute_interactive(sanitized_cmd, timeout=timeout)
                else:
                    result = await self.bash_adapter.execute(sanitized_cmd, timeout=timeout)
            
            # Truncate output if it's too large
            stdout, stderr, code = result
            if len(stdout) > self.resource_limits['max_output_size']:
                truncated = stdout[:self.resource_limits['max_output_size']] + "\n... [OUTPUT TRUNCATED DUE TO SIZE]"
                stdout = truncated
                
            if len(stderr) > self.resource_limits['max_output_size']:
                truncated = stderr[:self.resource_limits['max_output_size']] + "\n... [ERROR OUTPUT TRUNCATED DUE TO SIZE]"
                stderr = truncated
            
            # Log execution time for performance tracking
            execution_time = time.time() - start_time
            self.stats['last_execution_time'] = execution_time
            self.stats['total_execution_time'] += execution_time
            self.stats['commands_executed'] += 1
            
            # Update command record
            cmd_record.update({
                'end_time': time.time(),
                'execution_time': execution_time,
                'exit_code': code,
                'success': code == 0
            })
            
            # Check for timeout in stderr (set by our shell adapter)
            if "Command timed out after" in stderr:
                logger.warning(f"Command timed out after {timeout}s: {sanitized_cmd[:80]}")
                self.stats['timeout_commands'] = self.stats.get('timeout_commands', 0) + 1
            
            # Save command execution data to memory for adaptive learning
            self.memory_manager.save_document(
                f"command_execution_{int(time.time())}",
                f"Command: {sanitized_cmd}\nType: {command_type}\nExecution Time: {execution_time:.2f}s\nExit Code: {code}",
                tags=["command_execution", command_type, "success" if code == 0 else "failure"],
                metadata={
                    "command": sanitized_cmd,
                    "type": command_type,
                    "execution_time": execution_time,
                    "exit_code": code,
                    "timeout_used": timeout
                }
            )
            
            if execution_time > 5.0:  # Log slow commands
                logger.warning(f"Slow command execution: {execution_time:.2f}s for: {sanitized_cmd[:80]}")
                
            return (stdout, stderr, code)
            
        except SecurityWarning as security_error:
            # Log security warnings but still execute the command
            error_msg = str(security_error)
            logger.warning(f"Security warning (ignored in unrestricted mode): {error_msg}")
            # Continue with command execution despite security warning
            sanitized_cmd = command.strip()
            if command_type == 'python':
                # Execute Python code
                result = await self.bash_adapter.execute(f"python -c \"{sanitized_cmd}\"", timeout=timeout)
            else:
                # Execute bash command
                result = await self.bash_adapter.execute(sanitized_cmd, timeout=timeout)
            return result
            
        except asyncio.TimeoutError:
            # Handle timeout at this level too
            error_msg = f"Command execution timed out after {timeout} seconds"
            logger.error(error_msg)
            self.stats['errors'] += 1
            self.stats['timeout_commands'] = self.stats.get('timeout_commands', 0) + 1
            return ("", error_msg, 1)
            
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg)
            self.stats['errors'] += 1
            return ("", error_msg, 1)

    # File operations methods
    async def view_file(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """
        Read and return file contents.
        
        Args:
            file_path: Path to the file
            offset: Line number to start reading from (0-indexed)
            limit: Maximum number of lines to read
            
        Returns:
            File contents as string
        """
        try:
            logger.info(f"Reading file: {file_path}")
            result = self.file_ops.view(file_path, offset, limit)
            self.stats['file_operations'] += 1
            
            # Log file read to memory
            self.memory_manager.save_document(
                f"file_view_{int(time.time())}",
                f"Read file: {file_path} (offset={offset}, limit={limit})",
                tags=["file_operation", "view"],
                metadata={
                    "path": file_path,
                    "offset": offset,
                    "limit": limit,
                    "operation": "view"
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            self.stats['errors'] += 1
            return f"Error reading file: {str(e)}"
    
    async def edit_file(self, file_path: str, old_string: str, new_string: str) -> str:
        """
        Edit file by replacing text.
        
        Args:
            file_path: Path to the file
            old_string: Text to replace
            new_string: New text to insert
            
        Returns:
            Result message
        """
        try:
            logger.info(f"Editing file: {file_path}")
            result = self.file_ops.edit(file_path, old_string, new_string)
            self.stats['file_operations'] += 1
            
            # Log file edit to memory
            self.memory_manager.save_document(
                f"file_edit_{int(time.time())}",
                f"Edited file: {file_path}",
                tags=["file_operation", "edit"],
                metadata={
                    "path": file_path,
                    "operation": "edit"
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            self.stats['errors'] += 1
            return f"Error editing file: {str(e)}"
    
    async def replace_file(self, file_path: str, content: str) -> str:
        """
        Replace file contents or create new file.
        
        Args:
            file_path: Path to the file
            content: New file content
            
        Returns:
            Result message
        """
        try:
            logger.info(f"Replacing/creating file: {file_path}")
            result = self.file_ops.replace(file_path, content)
            self.stats['file_operations'] += 1
            
            # Log file replacement to memory
            self.memory_manager.save_document(
                f"file_replace_{int(time.time())}",
                f"Replaced file: {file_path}",
                tags=["file_operation", "replace"],
                metadata={
                    "path": file_path,
                    "operation": "replace",
                    "size": len(content)
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Error replacing file {file_path}: {e}")
            self.stats['errors'] += 1
            return f"Error replacing file: {str(e)}"
    
    async def glob_search(self, pattern: str, path: Optional[str] = None) -> List[str]:
        """
        Find files matching a pattern.
        
        Args:
            pattern: Glob pattern to match
            path: Directory to search in (defaults to current directory)
            
        Returns:
            List of matching file paths
        """
        try:
            logger.info(f"Glob search: {pattern} in {path or 'current directory'}")
            result = self.file_ops.glob_tool(pattern, path)
            self.stats['file_operations'] += 1
            
            # Log glob search to memory
            self.memory_manager.save_document(
                f"glob_search_{int(time.time())}",
                f"Glob search: {pattern} in {path or 'current directory'}",
                tags=["file_operation", "glob", "search"],
                metadata={
                    "pattern": pattern,
                    "path": path,
                    "operation": "glob",
                    "matches": len(result)
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Error in glob search: {e}")
            self.stats['errors'] += 1
            return [f"Error in glob search: {str(e)}"]
    
    async def grep_search(self, pattern: str, include: Optional[str] = None, 
                         path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for content in files.
        
        Args:
            pattern: Regex pattern to search for
            include: File pattern to include
            path: Directory to search in
            
        Returns:
            List of dictionaries with match info
        """
        try:
            logger.info(f"Grep search: {pattern} in {path or 'current directory'}")
            result = self.file_ops.grep_tool(pattern, include, path)
            self.stats['file_operations'] += 1
            
            # Log grep search to memory
            self.memory_manager.save_document(
                f"grep_search_{int(time.time())}",
                f"Grep search: {pattern} in {path or 'current directory'}",
                tags=["file_operation", "grep", "search"],
                metadata={
                    "pattern": pattern,
                    "include": include,
                    "path": path,
                    "operation": "grep",
                    "matches": len(result)
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Error in grep search: {e}")
            self.stats['errors'] += 1
            return [{"error": f"Error in grep search: {str(e)}"}]
    
    async def list_directory(self, path: str) -> Dict[str, Any]:
        """
        List contents of a directory.
        
        Args:
            path: Directory path to list
            
        Returns:
            Dictionary with directory contents
        """
        try:
            logger.info(f"Listing directory: {path}")
            result = self.file_ops.ls(path)
            self.stats['file_operations'] += 1
            
            # Log directory listing to memory
            self.memory_manager.save_document(
                f"ls_{int(time.time())}",
                f"Listed directory: {path}",
                tags=["file_operation", "ls", "directory"],
                metadata={
                    "path": path,
                    "operation": "ls"
                }
            )
            
            return result
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            self.stats['errors'] += 1
            return {"error": f"Error listing directory: {str(e)}"}

    def get_stats(self) -> Dict:
        """Return system control statistics"""
        return {
            **self.stats,
            'command_history_size': len(self.command_history),
            'avg_execution_time': (self.stats['total_execution_time'] / max(1, self.stats['commands_executed'])),
            'error_rate': (self.stats['errors'] / max(1, self.stats['commands_executed'] + self.stats['file_operations']))
        }

    def cleanup(self):
        """Clean up resources and save execution history"""
        try:
            # Save command history to memory
            history_file = Path("memory/state/command_history.json")
            history_file.parent.mkdir(exist_ok=True)
            
            # Only keep the last 1000 commands
            history_to_save = self.command_history[-1000:] if len(self.command_history) > 1000 else self.command_history
            
            import json
            with open(history_file, 'w') as f:
                json.dump(history_to_save, f, indent=2, default=str)
                
            # Clear adapter history
            self.bash_adapter.clear_history()
            
            logger.info(f"Command history saved, {len(history_to_save)} entries")
        except Exception as e:
            logger.error(f"Error during system control cleanup: {e}")
            
    async def monitor_resources(self):
        """Monitor system resources (memory, disk) in a background task"""
        try:
            # Check disk space in memory directory
            memory_path = Path("memory")
            if memory_path.exists():
                # Get disk usage using df command
                cmd = f"du -sh {memory_path}"
                stdout, stderr, code = await self.bash_adapter.execute(cmd)
                if code == 0:
                    disk_usage = stdout.strip()
                    logger.info(f"Memory directory size: {disk_usage}")
                    
                    # Save memory stats
                    self.memory_manager.save_document(
                        "resource_monitoring",
                        f"Memory directory size: {disk_usage}",
                        tags=["monitoring", "disk_usage"],
                        metadata={"disk_usage": disk_usage}
                    )
        except Exception as e:
            logger.error(f"Error monitoring resources: {e}")
