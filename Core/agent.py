import asyncio
import logging
import os
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from Clients.LLM import get_llm_client
from Memory.Manager.memory_manager import MemoryManager
from Tools.System.shell_adapter import ShellAdapter
from Tools.File.file_operations import FileOperations
from Tools.Search.search_tools import SearchTools
from Tools.Package.package_manager import PackageManager
from Core.task_manager import TaskManager
from Core.session_manager import SessionManager
from Output.display_manager import DisplayManager

logger = logging.getLogger(__name__)

class CommandResult:
    def __init__(self, stdout: str, stderr: str, code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.code = code
        self.success = (code == 0)
        self.timestamp = datetime.now()

    @property
    def output(self) -> str:
        return self.stdout if self.stdout else self.stderr

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stdout': self.stdout,
            'stderr': self.stderr,
            'code': self.code,
            'success': self.success,
            'timestamp': self.timestamp.isoformat()
        }

class CommandExtractor:
    COMMAND_TAGS = ['bash', 'python']
    THINKING_TAG = 'thinking'
    DECISION_TAG = 'decision'
    PLAN_TAG = 'plan'
    SUMMARY_TAG = 'summary'
    TASK_TAG = 'task'
    SUBTASK_TAG = 'subtask'
    FILE_OP_TAGS = ['view', 'edit', 'replace', 'glob', 'grep', 'ls']
    USER_INPUT_TAG = 'user_input'

    @staticmethod
    def extract_commands(response: str) -> List[Tuple[str, str]]:
        commands = []
        CommandExtractor._extract_tag_commands(response, CommandExtractor.COMMAND_TAGS, commands)
        CommandExtractor._extract_tag_commands(response, CommandExtractor.FILE_OP_TAGS, commands)
        return commands

    @staticmethod
    def _extract_tag_commands(response: str, tags: List[str], commands: List[Tuple[str, str]]) -> None:
        for tag in tags:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = list(re.finditer(pattern, response, re.DOTALL))
            if matches:
                for match in matches:
                    command = match.group(1)
                    if command:
                        # Removed full strip to preserve indentation. Only strip trailing newlines.
                        command = command.rstrip('\r\n')
                        commands.append((tag, command))
            else:
                open_tag_pattern = f"<{tag}>"
                close_tag_pattern = f"</{tag}>"
                starts = [m.end() for m in re.finditer(open_tag_pattern, response)]
                ends = [m.start() for m in re.finditer(close_tag_pattern, response)]
                for start in starts:
                    valid_ends = [e for e in ends if e > start]
                    if valid_ends:
                        end = min(valid_ends)
                        command = response[start:end]
                        if command:
                            command = command.rstrip('\r\n')
                            commands.append((tag, command))

    @staticmethod
    def extract_thinking(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.THINKING_TAG)

    @staticmethod
    def extract_decision(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.DECISION_TAG)

    @staticmethod
    def extract_plan(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.PLAN_TAG)

    @staticmethod
    def extract_summary(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.SUMMARY_TAG)

    @staticmethod
    def extract_tasks(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.TASK_TAG)

    @staticmethod
    def extract_subtasks(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.SUBTASK_TAG)

    @staticmethod
    def extract_user_input_requests(response: str) -> List[str]:
        standard_requests = CommandExtractor._extract_tag_content(response, CommandExtractor.USER_INPUT_TAG)
        alt_pattern = r"\[PAUSE_FOR_USER_INPUT\](.*?)\[/PAUSE_FOR_USER_INPUT\]"
        alt_matches = re.finditer(alt_pattern, response, re.DOTALL)
        alt_requests = [match.group(1).strip() for match in alt_matches]
        return standard_requests + alt_requests

    @staticmethod
    def _extract_tag_content(response: str, tag: str) -> List[str]:
        pattern = f"<{tag}>(.*?)</{tag}>"
        matches = list(re.finditer(pattern, response, re.DOTALL))
        results = [m.group(1).strip() for m in matches]
        if not results:
            open_tag_pattern = f"<{tag}>"
            close_tag_pattern = f"</{tag}>"
            starts = [m.end() for m in re.finditer(open_tag_pattern, response)]
            ends = [m.start() for m in re.finditer(close_tag_pattern, response)]
            for start in starts:
                valid_ends = [e for e in ends if e > start]
                if valid_ends:
                    end = min(valid_ends)
                    content = response[start:end].strip()
                    if content:
                        results.append(content)
        return results

    @staticmethod
    def extract_heredocs(response: str) -> List[Dict[str, str]]:
        heredocs = []
        heredoc_pattern = r'cat\s*<<\s*EOF\s*>\s*([^\n]+)(.*?)EOF'
        matches = re.finditer(heredoc_pattern, response, re.DOTALL)
        for match in matches:
            filename = match.group(1).strip()
            content = match.group(2)
            heredocs.append({'filename': filename, 'content': content})
        if not heredocs:
            current_doc = None
            content_lines = []
            for line in response.split('\n'):
                if not current_doc and ('cat << EOF >' in line or 'cat <<EOF >' in line):
                    parts = line.strip().split('>')
                    if len(parts) > 1:
                        current_doc = parts[1].strip()
                        continue
                elif line.strip() == 'EOF' and current_doc:
                    heredocs.append({
                        'filename': current_doc,
                        'content': '\n'.join(content_lines)
                    })
                    current_doc = None
                    content_lines = []
                    continue
                if current_doc:
                    content_lines.append(line)
        return heredocs

    @staticmethod
    def is_exit_command(command_type: str, command: str) -> bool:
        lower_cmd = command.strip().lower()
        exit_cmds = {"exit", "quit", "bye", "done"}
        if lower_cmd in exit_cmds:
            return True
        for exit_cmd in exit_cmds:
            if lower_cmd.startswith(f"{exit_cmd} "):
                return True
        return False

class SystemControl:
    """
    Manages system interactions including file operations and shell commands.
    """
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.shell_adapter = ShellAdapter()
        self.file_operations = FileOperations()
        self.search_tools = SearchTools()
        self.package_manager = PackageManager()
        self.display_manager = DisplayManager()
    
    async def execute_command(self, cmd_type: str, command: str, 
                              interactive: bool = False, timeout: int = 30) -> Tuple[str, str, int]:
        if self.test_mode:
            logger.info(f"TEST MODE: Would execute {cmd_type}: {command}")
            test_result = {"command": command, "result": {"stdout": f"[TEST MODE] Would execute: {command}", "stderr": "", "code": 0, "success": True}}
            self.display_manager.display_command_result(command, test_result["result"])
            return f"[TEST MODE] Would execute: {command}", "", 0
        
        try:
            result = None
            stdout, stderr, code = "", "", 1
            
            if cmd_type == "bash":
                stdout, stderr, code = await self.shell_adapter.execute_command(command, timeout)
            elif cmd_type == "python":
                python_cmd = f"python3 -c \"{command}\""
                stdout, stderr, code = await self.shell_adapter.execute_command(python_cmd, timeout)
            else:
                stderr = f"Unsupported command type: {cmd_type}"
                code = 1
            
            # Display result using the output formatter
            result_dict = {
                "stdout": stdout,
                "stderr": stderr,
                "code": code,
                "success": (code == 0)
            }
            self.display_manager.display_command_result(command, result_dict)
            
            return stdout, stderr, code
        except Exception as e:
            logger.error(f"Error executing {cmd_type} command: {e}")
            error_msg = str(e)
            
            # Display error using the output formatter
            self.display_manager.display_api_error(error_msg)
            
            return "", error_msg, 1
    
    async def view_file(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return self.file_operations.view(file_path, offset, limit)
    
    async def edit_file(self, file_path: str, old_string: str, new_string: str) -> str:
        return self.file_operations.edit(file_path, old_string, new_string)
    
    async def replace_file(self, file_path: str, content: str) -> str:
        return self.file_operations.replace(file_path, content)
    
    async def glob_search(self, pattern: str, path: Optional[str] = None) -> List[str]:
        return self.search_tools.glob_tool(pattern, path)
    
    async def grep_search(self, pattern: str, include: Optional[str] = None, 
                          path: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.search_tools.grep_tool(pattern, include, path)
    
    async def list_directory(self, path: str) -> Dict[str, Any]:
        return self.search_tools.ls(path)
    
    async def install_package(self, package_name: str, package_type: str = "python", 
                             version: Optional[str] = None) -> str:
        if package_type == "python":
            return await self.package_manager.install_python_package(package_name, version)
        elif package_type == "npm":
            return await self.package_manager.install_npm_package(package_name, version)
        elif package_type == "system":
            return await self.package_manager.install_system_package(package_name)
        elif package_type == "pacman":
            return await self.package_manager.install_pacman_package(package_name)
        else:
            return f"Unsupported package type: {package_type}"
    
    async def check_package(self, package_name: str, package_type: str = "python") -> Dict[str, Any]:
        """
        Check if a package is installed and get its information.
        
        Args:
            package_name: The name of the package to check
            package_type: The type of package manager to use (python, npm, system, pacman)
            
        Returns:
            Dictionary with package information
        """
        if package_type == "python":
            return await self.package_manager.check_python_package(package_name)
        elif package_type == "pacman":
            return await self.package_manager.check_pacman_package(package_name) 
        else:
            return {
                "installed": False,
                "name": package_name,
                "error": f"Package checking not implemented for {package_type}"
            }
    
    async def monitor_resources(self) -> Dict[str, Any]:
        """Monitor system resources usage"""
        if self.test_mode:
            return {"status": "test_mode"}
        
        try:
            # Basic resource monitoring
            cmd = "free -h && df -h | grep '^/dev' && ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -n 5"
            stdout, stderr, exit_code = await self.shell_adapter.execute_command(cmd)
            
            if exit_code == 0:
                return {
                    "status": "ok",
                    "data": stdout
                }
            else:
                return {
                    "status": "error",
                    "error": stderr
                }
        except Exception as e:
            logger.error(f"Error monitoring resources: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def cleanup(self):
        """Clean up any resources"""
        self.shell_adapter.close_interactive_shell()

class AutonomousAgent:
    def __init__(
        self,
        memory_manager: MemoryManager = None,
        session_manager: SessionManager = None,
        api_key: str = "",
        model: str = "deepseek",
        test_mode: bool = False
    ):
        if not api_key:
            raise ValueError("API key required")
        self.last_assistant_response = None
        self.paused_for_human_context = False
        self.memory_manager = memory_manager or MemoryManager()
        self.memory_path = self.memory_manager.base_path
        self._setup_storage()
        self.system_control = SystemControl(test_mode=test_mode)
        
    def _setup_storage(self):
        """Set up storage directories for the agent"""
        try:
            # Ensure necessary directories exist
            for directory in ["tasks", "reflections", "notes", "working_memory", "temporal"]:
                dir_path = self.memory_path / directory
                dir_path.mkdir(exist_ok=True, parents=True)
        except Exception as e:
            logger.error(f"Error setting up storage directories: {e}")
        self.agent_id = str(uuid.uuid4())[:8]
        self.agent_state = {
            'started_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'commands_executed': 0,
            'tasks_completed': 0,
            'memory_operations': 0,
            'status': 'initializing',
            'last_error': None,
            'current_task': None,
        }
        if not (self.memory_path / "vector_index").exists():
            try:
                system_prompt_path = Path("config/system_prompt.md")
                if system_prompt_path.exists():
                    self.memory_manager.save_document(
                        "system_guide",
                        system_prompt_path.read_text(),
                        tags=["system", "guide", "permanent"],
                        permanent=True
                    )
                    self.memory_manager.save_document(
                        "agent_identity",
                        f"Agent ID: {self.agent_id}\nInitialized: {self.agent_state['started_at']}\nModel: {model}",
                        tags=["system", "identity", "permanent"],
                        permanent=True
                    )
            except Exception as e:
                logger.error(f"Error seeding memory: {e}")
        self.reflections = []
        self.planned_steps = []
        self.executive_summary = ""
        self.llm = get_llm_client(model, api_key)
        self.model_name = model
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.command_extractor = CommandExtractor()
        self.should_exit = False
        self.command_history = []
        self.heartbeat_task = None
        self.resource_monitor_task = None
        self.test_mode = test_mode
        self.local_conversation_history: List[Dict[str, str]] = []
        self.working_memory: Dict[str, Any] = {}
        self.agent_state['status'] = 'ready'

    # ... [rest of the AutonomousAgent class remains unchanged]
    # Since we're not changing the core behavior, just importing from new locations
