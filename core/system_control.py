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

class SystemControl:
    def __init__(self, preferred_shell: str = 'bash', test_mode: bool = False):
        self.memory_manager = MemoryManager()
        self.memory_path = self.memory_manager.base_path
        self.working_dir = Path.cwd()
        self.preferred_shell = preferred_shell
        self.test_mode = test_mode
        self.bash_adapter = ShellAdapter(test_mode=self.test_mode, working_dir=self.working_dir)
        self.file_ops = FileOperations()
        self.command_history: List[Dict] = []
        self.resource_limits = {
            'max_execution_time': 120,
            'max_output_size': 1024 * 1024,
            'max_temp_files': 100,
            'interactive_timeout': 180
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
        return command.strip()

    async def execute_command(self, command_type: str, command: str, interactive: bool = False, 
                              timeout: int = None) -> Tuple[str, str, int]:
        try:
            if timeout is None:
                timeout = self.resource_limits['max_execution_time']
            sanitized_cmd = self._sanitize_command(command)
            logger.info(f"Executing command: {sanitized_cmd}")
            start_time = time.time()
            cmd_record = {'command': sanitized_cmd, 'type': command_type,'start_time': start_time,
                          'interactive': interactive,'timeout': timeout}
            self.command_history.append(cmd_record)
            if command_type == 'python':
                content = sanitized_cmd
                tmp_dir = self.memory_path / "temp"
                tmp_dir.mkdir(exist_ok=True)
                filename = f"exec_{int(time.time())}_{hash(content) % 10000}.py"
                tmp_file = tmp_dir / filename
                temp_files = list(tmp_dir.glob("exec_*.py"))
                if len(temp_files) > self.resource_limits['max_temp_files']:
                    temp_files.sort(key=lambda f: f.stat().st_mtime)
                    for old_file in temp_files[:-self.resource_limits['max_temp_files']]:
                        try:
                            old_file.unlink()
                        except:
                            pass
                with open(tmp_file, 'w') as f:
                    f.write(content)
                actual_cmd = f"python {tmp_file}"
                if interactive:
                    result = await self.bash_adapter.execute_interactive(actual_cmd, timeout=timeout)
                else:
                    result = await self.bash_adapter.execute(actual_cmd, timeout=timeout)
                logger.info(f"Python script at {tmp_file}")
            else:
                if interactive:
                    result = await self.bash_adapter.execute_interactive(sanitized_cmd, timeout=timeout)
                else:
                    result = await self.bash_adapter.execute(sanitized_cmd, timeout=timeout)
            stdout, stderr, code = result
            if len(stdout) > self.resource_limits['max_output_size']:
                stdout = stdout[:self.resource_limits['max_output_size']] + "\n...[TRUNCATED]..."
            if len(stderr) > self.resource_limits['max_output_size']:
                stderr = stderr[:self.resource_limits['max_output_size']] + "\n...[TRUNCATED]..."
            execution_time = time.time() - start_time
            self.stats['last_execution_time'] = execution_time
            self.stats['total_execution_time'] += execution_time
            self.stats['commands_executed'] += 1
            cmd_record.update({'end_time': time.time(),'execution_time': execution_time,
                               'exit_code': code,'success': (code == 0)})
            self.memory_manager.save_document(
                f"command_execution_{int(time.time())}",
                f"Cmd: {sanitized_cmd}\nType: {command_type}\nTime: {execution_time:.2f}s\nExit: {code}",
                tags=["command_execution", command_type, "success" if code == 0 else "failure"],
                metadata={"command": sanitized_cmd,"type": command_type,"time": execution_time,"exit": code}
            )
            return (stdout, stderr, code)
        except asyncio.TimeoutError:
            msg = f"Timed out after {timeout} seconds"
            logger.error(msg)
            self.stats['errors'] += 1
            self.stats['timeout_commands'] = self.stats.get('timeout_commands', 0) + 1
            return ("", msg, 1)
        except Exception as e:
            err = f"Error executing command: {e}"
            logger.error(err)
            self.stats['errors'] += 1
            return ("", err, 1)

    async def view_file(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        try:
            logger.info(f"view_file: {file_path}")
            result = self.file_ops.view(file_path, offset, limit)
            self.stats['file_operations'] += 1
            self.memory_manager.save_document(
                f"file_view_{int(time.time())}",
                f"Viewed file: {file_path} (offset={offset}, limit={limit})",
                tags=["file_operation","view"],
                metadata={"path": file_path,"offset": offset,"limit": limit}
            )
            return result
        except Exception as e:
            logger.error(f"Error view_file {file_path}: {e}")
            self.stats['errors'] += 1
            return f"Error reading file: {str(e)}"

    async def edit_file(self, file_path: str, old_string: str, new_string: str) -> str:
        try:
            logger.info(f"edit_file: {file_path}")
            result = self.file_ops.edit(file_path, old_string, new_string)
            self.stats['file_operations'] += 1
            self.memory_manager.save_document(
                f"file_edit_{int(time.time())}",
                f"Edited file: {file_path}",
                tags=["file_operation","edit"],
                metadata={"path": file_path}
            )
            return result
        except Exception as e:
            logger.error(f"Error edit_file {file_path}: {e}")
            self.stats['errors'] += 1
            return f"Error editing file: {str(e)}"

    async def replace_file(self, file_path: str, content: str) -> str:
        try:
            logger.info(f"replace_file: {file_path}")
            result = self.file_ops.replace(file_path, content)
            self.stats['file_operations'] += 1
            self.memory_manager.save_document(
                f"file_replace_{int(time.time())}",
                f"Replaced file: {file_path}",
                tags=["file_operation","replace"],
                metadata={"path": file_path,"size": len(content)}
            )
            return result
        except Exception as e:
            logger.error(f"Error replace_file {file_path}: {e}")
            self.stats['errors'] += 1
            return f"Error replacing file: {str(e)}"

    async def glob_search(self, pattern: str, path: Optional[str] = None) -> List[str]:
        try:
            logger.info(f"glob_search: {pattern} in {path or 'cwd'}")
            result = self.file_ops.glob_tool(pattern, path)
            self.stats['file_operations'] += 1
            self.memory_manager.save_document(
                f"glob_search_{int(time.time())}",
                f"Glob: {pattern} in {path or 'cwd'}",
                tags=["file_operation","glob"],
                metadata={"pattern": pattern,"path": path,"matches": len(result)}
            )
            return result
        except Exception as e:
            logger.error(f"Error glob_search: {e}")
            self.stats['errors'] += 1
            return [f"Error: {str(e)}"]

    async def grep_search(self, pattern: str, include: Optional[str] = None, 
                         path: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            logger.info(f"grep_search: {pattern} in {path or 'cwd'}")
            result = self.file_ops.grep_tool(pattern, include, path)
            self.stats['file_operations'] += 1
            self.memory_manager.save_document(
                f"grep_search_{int(time.time())}",
                f"Grep: {pattern} in {path or 'cwd'}",
                tags=["file_operation","grep"],
                metadata={"pattern": pattern,"include": include,"path": path,"matches": len(result)}
            )
            return result
        except Exception as e:
            logger.error(f"Error grep_search: {e}")
            self.stats['errors'] += 1
            return [{"error": f"{str(e)}"}]

    async def list_directory(self, path: str) -> Dict[str, Any]:
        try:
            logger.info(f"ls: {path}")
            result = self.file_ops.ls(path)
            self.stats['file_operations'] += 1
            self.memory_manager.save_document(
                f"ls_{int(time.time())}",
                f"Listed directory: {path}",
                tags=["file_operation","ls"],
                metadata={"path": path}
            )
            return result
        except Exception as e:
            logger.error(f"Error listing dir {path}: {e}")
            self.stats['errors'] += 1
            return {"error": f"{str(e)}"}

    def get_stats(self) -> Dict:
        return {
            **self.stats,
            'command_history_size': len(self.command_history),
            'avg_execution_time': (self.stats['total_execution_time'] /
                                   max(1, self.stats['commands_executed'])),
            'error_rate': (self.stats['errors'] /
                           max(1, self.stats['commands_executed'] + self.stats['file_operations']))
        }

    def cleanup(self):
        try:
            history_file = self.memory_path / "state" / "command_history.json"
            history_file.parent.mkdir(exist_ok=True)
            history_to_save = self.command_history[-1000:] if len(self.command_history) > 1000 else self.command_history
            import json
            with open(history_file, 'w') as f:
                json.dump(history_to_save, f, indent=2, default=str)
            self.bash_adapter.clear_history()
            logger.info(f"Command history saved: {len(history_to_save)} entries")
        except Exception as e:
            logger.error(f"SystemControl cleanup error: {e}")

    async def monitor_resources(self):
        try:
            if self.memory_path.exists():
                cmd = f"du -sh {self.memory_path}"
                stdout, stderr, code = await self.bash_adapter.execute(cmd)
                if code == 0:
                    disk_usage = stdout.strip()
                    logger.info(f"Memory dir size: {disk_usage}")
                    self.memory_manager.save_document(
                        "resource_monitoring",
                        f"Memory dir: {disk_usage}",
                        tags=["monitoring","disk_usage"],
                        metadata={"disk_usage": disk_usage}
                    )
        except Exception as e:
            logger.error(f"Error monitoring resources: {e}")
