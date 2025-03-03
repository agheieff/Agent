import asyncio
import logging
import os
import json
import re
import time
import uuid
import select
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# Standardize on Clients/LLM implementation
from Clients.LLM import get_llm_client
# Use Memory directory implementations with robust handling for both interfaces
from Memory.Manager.memory_manager import MemoryManager
from Memory.Cache.memory_cache import MemoryCache
from Memory.Hierarchy.memory_hierarchy import MemoryHierarchy
from Memory.Preloader.memory_preloader import MemoryPreloader
# Standardize on Tools directory implementations
from Tools.System.shell_adapter import ShellAdapter
from Tools.File.file_operations import FileOperations
from Tools.Search.search_tools import SearchTools
from Tools.Package.package_manager import PackageManager
# Local components that don't have duplicates
from Core.task_manager import TaskManager
from Core.session_manager import SessionManager
from Output.display_manager import DisplayManager
# Atom of Thoughts components
from Core.aot.atom_decomposer import AtomDecomposer
from Core.aot.dag_manager import DAGManager
from Core.aot.atom_executor import AtomExecutor
from Core.aot.atom_contractor import AtomContractor

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
    """
    Extracts commands and other structured information from LLM responses.
    Handles both code execution and file operations.
    
    Commands are extracted from XML-style tags in the response.
    """
    
    # Command types
    COMMAND_TAGS = ['bash', 'python']
    
    # Thinking and planning tags
    THINKING_TAG = 'thinking'
    DECISION_TAG = 'decision'
    PLAN_TAG = 'plan'
    SUMMARY_TAG = 'summary'
    TASK_TAG = 'task'
    SUBTASK_TAG = 'subtask'
    
    # File operation tags with parameters:
    # <view>
    #   file_path: /path/to/file
    #   offset: 0 (optional)
    #   limit: 100 (optional)
    # </view>
    #
    # <edit>
    #   file_path: /path/to/file
    #   old_string: text to replace
    #   new_string: replacement text
    # </edit>
    #
    # <replace>
    #   file_path: /path/to/file
    #   content: new content for the file
    # </replace>
    #
    # <glob>
    #   pattern: *.py
    #   path: /path (optional)
    # </glob>
    #
    # <grep>
    #   pattern: regex
    #   include: *.py (optional)
    #   path: /path (optional)
    # </grep>
    #
    # <ls>
    #   path: /path/to/dir
    #   hide_hidden: false (optional, default is false - shows hidden files)
    # </ls>
    FILE_OP_TAGS = ['view', 'edit', 'replace', 'glob', 'grep', 'ls']
    
    # User interaction tags
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
            # First attempt: Try to extract using standard XML-style tag pattern
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = list(re.finditer(pattern, response, re.DOTALL))
            if matches:
                for match in matches:
                    command = match.group(1)
                    if command:
                        # Preserve indentation, only strip trailing newlines
                        command = command.rstrip('\r\n') 
                        commands.append((tag, command))
            else:
                # Second attempt: Handle potential malformed tags with newlines or spaces
                # This is especially important for file operation tags that may be split across lines
                
                # Match open and close tags, accounting for potential newlines/spaces
                open_tag_pattern = f"<{tag}[ \\t\\r\\n]*>"
                close_tag_pattern = f"</{tag}[ \\t\\r\\n]*>"
                
                # Find all occurrences
                starts = [(m.start(), m.end()) for m in re.finditer(open_tag_pattern, response, re.DOTALL)]
                ends = [(m.start(), m.end()) for m in re.finditer(close_tag_pattern, response, re.DOTALL)]
                
                # For each start tag, find the nearest matching end tag
                for start_pos, start_end in starts:
                    valid_ends = [(end_pos, end_end) for end_pos, end_end in ends if end_pos > start_end]
                    if valid_ends:
                        # Get the nearest end tag
                        end_pos, end_end = min(valid_ends, key=lambda x: x[0])
                        
                        # Extract the command between tags
                        command = response[start_end:end_pos]
                        if command:
                            # Clean up the command but preserve indentation
                            command = command.rstrip('\r\n')
                            commands.append((tag, command))
                
                # Log any unpaired tags for debugging
                if starts and not ends:
                    logger.warning(f"Found opening <{tag}> tags but no closing tags")
                elif ends and not starts:
                    logger.warning(f"Found closing </{tag}> tags but no opening tags")

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
    
    async def list_directory(self, path: str, hide_hidden: bool = False) -> Dict[str, Any]:
        """
        List files and directories in a path. 
        
        Args:
            path: Directory path to list
            hide_hidden: If True, hide files/directories that start with '.'
                         Default is False (show all files, including hidden)
        """
        return self.search_tools.ls(path, hide_hidden)
    
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
        model: str = "deepseek-reasoner",
        provider: str = "deepseek",
        test_mode: bool = False,
        config: Dict[str, Any] = None
    ):
        if not api_key:
            raise ValueError("API key required")
        self.api_key = api_key
        self.model_name = model
        self.provider = provider.lower()
        self.test_mode = test_mode
        self.config = config or {}
        self.last_assistant_response = None
        self.paused_for_human_context = False
        self.memory_manager = memory_manager or MemoryManager()
        self.memory_path = self.memory_manager.base_path
        self._setup_storage()
        self.system_control = SystemControl(test_mode=test_mode)
        self.session_manager = session_manager or SessionManager(self.memory_path, self.memory_manager)
        self.task_manager = TaskManager(self.memory_path)
        
        # Initialize Atom of Thoughts (AoT) components if enabled
        self.aot_enabled = self.config.get('aot', {}).get('enabled', False) or self.config.get('agent', {}).get('enable_aot', False)
        self.aot_decomposer = None
        self.aot_dag_manager = None
        self.aot_executor = None
        self.aot_contractor = None
        
        if self.aot_enabled:
            logger.info("Initializing Atom of Thoughts (AoT) components")
            self.aot_decomposer = AtomDecomposer(self.llm, self.config.get('aot', {}))
            self.aot_dag_manager = DAGManager(self.config.get('aot', {}))
            self.aot_executor = AtomExecutor(self.llm, self.config.get('aot', {}))
            self.aot_contractor = AtomContractor(self.llm, self.config.get('aot', {}))
        
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
                # Use proper path to system prompt in Config/SystemPrompts
                system_prompt_path = Path(__file__).parent.parent / "Config" / "SystemPrompts" / "system_prompt.md"
                if system_prompt_path.exists():
                    self.memory_manager.save_document(
                        "system_guide",
                        system_prompt_path.read_text(),
                        tags=["system", "guide", "permanent"],
                        permanent=True
                    )
                    self.memory_manager.save_document(
                        "agent_identity",
                        f"Agent ID: {self.agent_id}\nInitialized: {self.agent_state['started_at']}\nModel: {self.model_name}",
                        tags=["system", "identity", "permanent"],
                        permanent=True
                    )
            except Exception as e:
                logger.error(f"Error seeding memory: {e}")
        self.reflections = []
        self.planned_steps = []
        self.executive_summary = ""
        self.llm = get_llm_client(self.provider, self.api_key)
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.command_extractor = CommandExtractor()
        self.should_exit = False
        self.command_history = []
        self.heartbeat_task = None
        self.resource_monitor_task = None
        self.local_conversation_history: List[Dict[str, str]] = []
        self.working_memory: Dict[str, Any] = {}
        self.agent_state['status'] = 'ready'

    def _load_last_session(self) -> str:
        """Load the summary of the last session from memory"""
        try:
            summary_path = self.memory_path / "summaries" / "last_session.txt"
            if summary_path.exists():
                return summary_path.read_text()
            return ""
        except Exception as e:
            logger.error(f"Error loading last session summary: {e}")
            return ""
            
    async def run(self, initial_prompt: str, system_prompt: str = ""):
        """Run the agent with the given initial prompt and system prompt"""
        try:
            self.agent_state['status'] = 'running'
            self.current_conversation_id = f"session_{int(time.time())}"
            
            logger.info(f"Starting agent run with conversation ID: {self.current_conversation_id}")
            
            # Special handling for DeepSeek models
            if self.provider == "deepseek":
                # For DeepSeek models, we combine system prompt and initial prompt
                # and send it as the first user message with an empty system prompt
                logger.info("Using DeepSeek-specific prompt handling (combining system+user prompts)")
                combined_prompt = f"{system_prompt}\n\n{initial_prompt}" if system_prompt else initial_prompt
                self.local_conversation_history = [
                    {"role": "system", "content": ""},
                    {"role": "user", "content": combined_prompt}
                ]
                response = await self._generate_response("", combined_prompt)
            else:
                # For other models like Anthropic, use normal system prompt handling
                self.local_conversation_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": initial_prompt}
                ]
                response = await self._generate_response(system_prompt, initial_prompt)
            should_continue = True
            
            # Main conversation loop
            while should_continue and not self.should_exit:
                self.memory_manager.update_conversation_metrics(increment_turns=True)
                
                # Extract commands and plan steps from the response and determine next action
                response_state = await self._process_response(response)
                
                # Check if this is a result from auto-handling (type will be a dict with auto_continue flag)
                if isinstance(response_state, dict) and response_state.get("auto_continue"):
                    # We're auto-continuing with command results
                    response = response_state.get("next_response", "")
                    should_continue = True
                else:
                    # Standard boolean result
                    should_continue = response_state
                
                if should_continue and not self.should_exit:
                    # If agent is in autonomous mode and we processed commands successfully, 
                    # continue executing without waiting for user input
                    auto_continue = self.config.get("agent", {}).get("autonomous_mode", True) and not self.config.get("agent", {}).get("require_input", False)
                    
                    if auto_continue:
                        # Auto-continue by creating a synthetic user message to keep the conversation going
                        auto_message = "Continue with the next steps based on the results of the previous commands."
                        
                        # Add as user message to maintain conversation structure
                        self.local_conversation_history.append({
                            "role": "user",
                            "content": auto_message
                        })
                        
                        # Generate next response
                        response = await self._generate_response(None, auto_message)
                    else:
                        # Non-autonomous mode: get user input for the next turn
                        user_input = await self._get_user_input()
                        
                        if user_input.strip().lower() in ["exit", "quit", "bye"]:
                            should_continue = False
                            break
                        
                        # Process special commands
                        if user_input.strip().startswith('/'):
                            cmd = user_input.strip().lower()
                            if cmd == '/compact':
                                await self._compact_conversation()
                                user_input = "Continue where you left off. The conversation has been compacted to save context space."
                            elif cmd == '/help':
                                print("\nAvailable Slash Commands:")
                                print("  /help     - Show this help message")
                                print("  /compact  - Compact conversation history to save context space")
                                print("  /pause    - Pause to add additional context to the conversation")
                                print("  /auto     - Toggle autonomous mode on/off")
                                print("\nKeyboard Shortcuts:")
                                print("  Ctrl+Z    - Pause to add context (equivalent to /pause)")
                                print("  Ctrl+C    - Exit the agent")
                                user_input = "The user requested help with slash commands. I showed them the available commands. Please continue."
                            elif cmd == '/auto':
                                # Toggle autonomous mode
                                current_mode = self.config.get("agent", {}).get("autonomous_mode", True)
                                self.config.setdefault("agent", {})["autonomous_mode"] = not current_mode
                                print(f"\nAutonomous mode {'disabled' if current_mode else 'enabled'}.")
                                user_input = f"The user has {'disabled' if current_mode else 'enabled'} autonomous mode. Please {'wait for explicit user input after each step' if current_mode else 'continue autonomously without requiring user input between steps'}."
                        
                        # Generate the next response with user input
                        response = await self._generate_response(None, user_input)
            
            # Save session summary
            await self._save_session_summary()
            
            # Perform cleanup
            self.agent_state['status'] = 'completed'
            logger.info(f"Agent run completed for conversation ID: {self.current_conversation_id}")
            
            # Create a backup of the memory
            self.memory_manager.create_backup(force=True)
            
        except Exception as e:
            logger.error(f"Error in agent run: {e}")
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise
            
    async def _generate_response(self, system_prompt: Optional[str], user_input: str) -> str:
        """Generate a response from the LLM using Atom of Thoughts if enabled"""
        try:
            # Update conversation history 
            if system_prompt is not None:
                # Only add system prompt on first turn
                self.local_conversation_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            else:
                # Add user input to history
                self.local_conversation_history.append({
                    "role": "user", 
                    "content": user_input
                })
            
            # Use Atom of Thoughts if enabled and this isn't the first turn with system prompt
            # Also check if the user has explicitly requested direct response (no AoT)
            should_use_aot = (
                self.aot_enabled and 
                self.aot_decomposer is not None and 
                system_prompt is None and
                not any(marker in user_input.lower() for marker in ['direct:', 'no_aot:'])
            )
            
            if should_use_aot:
                # Generate response using Atom of Thoughts
                logger.info("Using Atom of Thoughts for response generation")
                response = await self._generate_with_aot(user_input)
            else:
                # Generate standard response
                response = await self.llm.generate_response(self.local_conversation_history)
            
            # Save response to history
            self.local_conversation_history.append({
                "role": "assistant",
                "content": response
            })
            
            # Display the response
            print(f"\n{response}\n")
            
            # Save the last response for reference 
            self.last_assistant_response = response
            
            # Update last active time
            self.agent_state['last_active'] = datetime.now().isoformat()
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            error_message = f"I encountered an error while generating a response: {str(e)}"
            self.local_conversation_history.append({
                "role": "assistant",
                "content": error_message
            })
            return error_message
            
    async def _generate_with_aot(self, user_input: str) -> str:
        """
        Generate a response using the Atom of Thoughts (AoT) approach.
        
        This implements the AoT process:
        1. Decompose the problem into atomic components
        2. Create a DAG representing dependencies
        3. Execute atoms according to the DAG
        4. Contract results into a final response
        """
        start_time = time.time()
        logger.info("Starting AoT response generation")
        
        try:
            # 1. Decompose the problem into atoms
            conversation_history = self.local_conversation_history[:-1]  # Exclude current user input
            atoms = await self.aot_decomposer.decompose(user_input, conversation_history)
            logger.info(f"Problem decomposed into {len(atoms)} atoms")
            
            # 2. Create the DAG structure
            dag = self.aot_dag_manager.create_dag(atoms)
            logger.info(f"Created DAG with {len(dag.execution_levels)} execution levels")
            
            # 3. Execute the atoms according to the DAG dependencies
            atom_results = await self.aot_executor.execute_atoms(dag, conversation_history)
            completed_atoms = sum(1 for r in atom_results.values() if r.status == AtomStatus.COMPLETED)
            logger.info(f"Executed {len(atom_results)} atoms, {completed_atoms} completed successfully")
            
            # 4. Contract the atom results into a coherent response
            response = await self.aot_contractor.contract_atoms(atom_results, user_input, conversation_history)
            
            # Record timing information
            elapsed_time = time.time() - start_time
            logger.info(f"AoT response generation completed in {elapsed_time:.2f}s")
            
            # Return the final response
            return response
            
        except Exception as e:
            logger.error(f"Error in AoT response generation: {e}")
            # Fall back to standard response generation
            logger.info("Falling back to standard response generation")
            return await self.llm.generate_response(self.local_conversation_history)
            
    async def _process_response(self, response: str) -> bool:
        """Process commands and handle user input requests in the response"""
        try:
            # Get verbosity level for logging
            verbose_level = self.config.get("output", {}).get("verbose_level", 0)
            
            # Extract commands
            commands = self.command_extractor.extract_commands(response)
            
            # Extract user input requests
            input_requests = self.command_extractor.extract_user_input_requests(response)
            
            # Extract thinking and planning in verbose mode
            thinking = self.command_extractor.extract_thinking(response)
            planning = self.command_extractor.extract_plan(response)
            
            # Log the extracted elements if in verbose mode
            if verbose_level >= 2:
                if commands:
                    print(f"\n[VERBOSE] Extracted {len(commands)} commands")
                if input_requests:
                    print(f"[VERBOSE] Extracted {len(input_requests)} input requests")
                if thinking:
                    print(f"[VERBOSE] Extracted {len(thinking)} thinking blocks")
                if planning:
                    print(f"[VERBOSE] Extracted {len(planning)} planning blocks")
            
            # Process user input requests with improved autonomy
            if input_requests:
                # Check if input is essential or can be skipped for better autonomy
                should_ask_for_input = False
                input_text = input_requests[0].lower()
                
                # Analyze the request - only request input for truly critical things
                critical_terms = ["confirm", "choose", "select", "password", "must", "required", 
                                 "need your", "your preference", "permission", "authorize", "authentication", 
                                 "credentials", "token", "key", "secret", "decide", "choice", "options"]
                
                # Check if the request contains critical terms indicating user input is essential
                is_critical = any(term in input_text for term in critical_terms)
                
                # In autonomous mode, only ask for input if it seems critical
                # The more verbose the mode, the more likely we'll ask for input
                if is_critical:
                    should_ask_for_input = True
                    
                    if verbose_level >= 1:
                        print(f"[VERBOSE] Input request considered critical")
                        print(f"[VERBOSE] Will ask for input: {should_ask_for_input}")
                elif verbose_level >= 3:
                    # Only ask for input in the highest verbosity mode for non-critical items
                    should_ask_for_input = True
                    if verbose_level >= 1:
                        print(f"[VERBOSE] Input request considered non-critical but asking due to high verbosity")
                        print(f"[VERBOSE] Will ask for input: {should_ask_for_input}")
                
                # If we're not asking for input, log this in verbose mode
                if not should_ask_for_input and verbose_level >= 1:
                    print(f"[VERBOSE] Autonomously continuing without asking for non-critical input")
                    # Use a default response to continue without user input
                    default_response = "Please continue with what you think is best."
                    user_input = default_response
                else:
                    # We need to ask for input, show the prompt
                    print("\n" + "=" * 60)
                    print("| AGENT REQUESTING INPUT |")
                    print("-" * 60)
                    print(input_requests[0])  # Take the first input request
                    print("=" * 60 + "\n")
                    
                    # Get user input
                    user_input = await self._get_user_input()
                
                # Modify the last assistant message to include the user input request
                # instead of adding a new message, to maintain user-assistant alternation
                if self.local_conversation_history and self.local_conversation_history[-1]["role"] == "assistant":
                    last_response = self.local_conversation_history[-1]["content"]
                    modified_response = last_response + f"\n\n[User input received: {user_input}]"
                    self.local_conversation_history[-1]["content"] = modified_response
                    
                    # Now add the user input as a new message
                    self.local_conversation_history.append({
                        "role": "user",
                        "content": user_input
                    })
                    
                    # Generate new response with the input
                    new_response = await self._generate_response(None, user_input)
                    
                    # Return a dictionary indicating we're auto-continuing with user input results
                    return {
                        "auto_continue": True,
                        "next_response": new_response
                    }
                else:
                    # This shouldn't happen, but handle it just in case
                    print("Warning: Conversation history is in an unexpected state")
                    self.local_conversation_history.append({
                        "role": "user",
                        "content": user_input
                    })
                    
                    # Generate new response with the input
                    new_response = await self._generate_response(None, user_input)
                    
                    # Return a dictionary indicating we're auto-continuing with user input results
                    return {
                        "auto_continue": True,
                        "next_response": new_response
                    }
            
            # Get verbosity details
            auto_handle_output = verbose_level <= 1  # Only automatically handle output in less verbose modes
            
            # Process commands
            command_results = []  # Store results for auto-handling
            
            for cmd_type, command in commands:
                if self.command_extractor.is_exit_command(cmd_type, command):
                    self.should_exit = True
                    return False
                
                # Process file operations
                if cmd_type in self.command_extractor.FILE_OP_TAGS:
                    result = await self._process_file_operation(cmd_type, command)
                    if result:
                        command_results.append({
                            "type": cmd_type,
                            "command": command,
                            "output": result,
                            "success": "error" not in result.lower()
                        })
                    continue
                
                # Process bash or python commands
                if cmd_type in ["bash", "python"]:
                    # Execute the command and display result inline
                    command_preview = command.splitlines()[0]
                    if len(command_preview) > 60:
                        command_preview = command_preview[:57] + "..."
                    
                    if verbose_level >= 2:
                        print(f"[VERBOSE] Executing {cmd_type} command: {command_preview}")
                        
                    print(f"> {cmd_type}: {command_preview}", end="", flush=True)
                    
                    # Execute the command
                    stdout, stderr, code = await self.system_control.execute_command(cmd_type, command)
                    
                    # Store result for auto-handling
                    command_results.append({
                        "type": cmd_type,
                        "command": command,
                        "stdout": stdout,
                        "stderr": stderr,
                        "code": code,
                        "success": code == 0
                    })
                    
                    # Display result with nicer formatting
                    command_type_emoji = "🔄" if cmd_type == "bash" else "🐍" if cmd_type == "python" else "⚙️"
                    if code == 0:
                        print(f" {command_type_emoji} ✅")  # Success indicator with emoji
                    else:
                        print(f" {command_type_emoji} ❌ (exit code: {code})")  # Error indicator with emoji
                        
                    # Show output based on verbosity with nicer formatting
                    if stdout or stderr:
                        output = stdout if stdout else stderr
                        
                        # Determine how many lines to show based on verbosity
                        if verbose_level >= 3:
                            max_preview_lines = 20
                        elif verbose_level >= 2:
                            max_preview_lines = 10
                        elif verbose_level >= 1:
                            max_preview_lines = 5
                        else:
                            max_preview_lines = 3
                        
                        # Show preview lines with nice formatting
                        print("  ┌─────────────────────────────────────────────────────")
                        lines = output.splitlines()
                        preview_lines = lines[:max_preview_lines]
                        for line in preview_lines:
                            print(f"  │ {line}")
                        if len(lines) > max_preview_lines:
                            remaining = len(lines) - max_preview_lines
                            print(f"  │ ... {remaining} more line{'s' if remaining != 1 else ''} ...")
                        print("  └─────────────────────────────────────────────────────")
                    
                    self.agent_state['commands_executed'] += 1
                    self.agent_state['last_active'] = datetime.now().isoformat()
                    
                    # Record command in history
                    self.command_history.append({
                        "command": command,
                        "type": cmd_type,
                        "timestamp": time.time(),
                        "success": code == 0,
                        "stdout": stdout,
                        "stderr": stderr
                    })
                    
                    # Add the result to memory
                    if self.memory_manager:
                        self.memory_manager.add_command_to_history(command, cmd_type, code == 0)
            
            # Automatically handle command results if appropriate
            if auto_handle_output and command_results and all(r.get("success", False) for r in command_results):
                # If we have successful commands, automatically continue with their output
                if verbose_level >= 1:
                    print("[VERBOSE] Automatically continuing with command results")
                
                # Create a summary of command results to add to conversation
                results_summary = "\n\nI've executed the following commands with these results:\n"
                for result in command_results:
                    cmd_type = result.get("type", "unknown")
                    cmd_preview = result.get("command", "").splitlines()[0][:40]
                    if cmd_type in self.command_extractor.FILE_OP_TAGS:
                        results_summary += f"- {cmd_type}: {cmd_preview}... - {result.get('output', 'No output')}\n"
                    else:
                        stdout = result.get("stdout", "").strip()
                        if stdout:
                            # Add a short preview of stdout
                            stdout_preview = stdout.splitlines()[0][:60]
                            if len(stdout.splitlines()) > 1 or len(stdout.splitlines()[0]) > 60:
                                stdout_preview += "..."
                            results_summary += f"- {cmd_type}: {cmd_preview}... - Output: {stdout_preview}\n"
                        else:
                            results_summary += f"- {cmd_type}: {cmd_preview}... - Completed successfully\n"
                
                results_summary += "\nPlease continue with the next steps based on these results."
                
                # Add as user message and generate response
                self.local_conversation_history.append({
                    "role": "user",
                    "content": results_summary
                })
                
                # Generate new response with the command results
                new_response = await self._generate_response(None, results_summary)
                
                # Return a dictionary indicating we're auto-continuing with command results
                return {
                    "auto_continue": True,
                    "next_response": new_response
                }
            
            # Extract other structured elements like thinking, plan, etc.
            thinking = self.command_extractor.extract_thinking(response)
            if thinking:
                for thought in thinking:
                    logger.debug(f"Agent thinking: {thought}")
            
            planning = self.command_extractor.extract_plan(response)
            if planning:
                for plan in planning:
                    self.planned_steps.append(plan.strip())
                    logger.info(f"Agent planned: {plan.strip()}")
                    
                    # Display plan to user
                    if len(planning) == 1:  # Only show if there's a single plan
                        print(f"\n--- PLAN ---\n{plan.strip()}\n")
            
            # Extract and display summary if present
            summaries = self.command_extractor.extract_summary(response)
            if summaries:
                print("\n--- SUMMARY ---")
                for summary in summaries:
                    print(f"{summary.strip()}")
                print()
            
            # Update conversation state in memory
            if self.memory_manager and self.current_conversation_id:
                self.memory_manager.save_conversation(
                    self.current_conversation_id,
                    self.local_conversation_history,
                    metadata={
                        "commands_executed": self.agent_state['commands_executed'],
                        "status": self.agent_state['status'],
                        "timestamp": time.time()
                    }
                )
                # Update memory operations counter using a robust approach
                try:
                    # First try using the memory_stats dictionary (Memory/Manager implementation)
                    if hasattr(self.memory_manager, 'memory_stats') and isinstance(self.memory_manager.memory_stats, dict):
                        self.memory_manager.memory_stats['memory_operations'] = self.memory_manager.memory_stats.get('memory_operations', 0) + 1
                    # Fall back to direct attribute (Core implementation)
                    elif hasattr(self.memory_manager, 'memory_operations'):
                        self.memory_manager.memory_operations += 1
                    # If neither exists, add the attribute
                    else:
                        self.memory_manager.memory_operations = 1
                    
                    # Also update our local tracking
                    self.agent_state['memory_operations'] += 1
                except Exception as e:
                    logger.error(f"Error updating memory operations: {e}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error processing response: {e}")
            return True  # Continue despite error
            
    async def _process_file_operation(self, op_type: str, command: str) -> str:
        """
        Process file operations extracted from the response
        
        Returns:
            str: A summary of the operation result for auto-handling
        """
        try:
            # More robust parsing for command parameters that handles multi-line values
            # First, normalize line endings
            command = command.replace('\r\n', '\n').strip()
            
            # More robust parameter parsing that handles multi-line values
            # and correctly processes parameters with special characters
            params = {}
            
            # Parse parameters using safer line-by-line parsing with better handling of indentation
            # This works well with the recommended XML format:
            # <edit>
            # file_path: /path/to/file.txt
            # old_string: multi-line
            #   text to
            #   replace
            # new_string: replacement
            #   text
            # </edit>
            
            lines = command.split('\n')
            current_key = None
            current_value = []
            
            for i, line in enumerate(lines):
                line = line.rstrip()
                
                # Check if this is a new parameter line (contains a colon and isn't indented)
                if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                    # Save previous parameter if there was one
                    if current_key:
                        params[current_key] = '\n'.join(current_value).strip()
                        logger.debug(f"Extracted parameter: {current_key} = {params[current_key][:30]}{'...' if len(params[current_key]) > 30 else ''}")
                    
                    # Start new parameter
                    parts = line.split(":", 1)
                    current_key = parts[0].strip()
                    current_value = [parts[1].strip()]
                elif current_key:
                    # This is a continuation line (part of the current parameter value)
                    current_value.append(line)
            
            # Save the last parameter
            if current_key and current_value:
                params[current_key] = '\n'.join(current_value).strip()
                logger.debug(f"Extracted parameter: {current_key} = {params[current_key][:30]}{'...' if len(params[current_key]) > 30 else ''}")
            
            # For backward compatibility, make sure we have at least empty parameters
            file_op_tags = ['view', 'edit', 'replace', 'glob', 'grep', 'ls']
            if op_type in file_op_tags:
                # Make sure we have at least the required parameters with default values
                if op_type == 'view' and 'file_path' not in params:
                    logger.error("Missing required file_path parameter for view operation")
                elif op_type == 'edit' and ('file_path' not in params or 'old_string' not in params or 'new_string' not in params):
                    logger.error(f"Missing required parameters for edit operation: {params.keys()}")
                elif op_type == 'replace' and ('file_path' not in params or 'content' not in params):
                    logger.error(f"Missing required parameters for replace operation: {params.keys()}")
                elif op_type == 'glob' and 'pattern' not in params:
                    logger.error("Missing required pattern parameter for glob operation")
                elif op_type == 'grep' and 'pattern' not in params:
                    logger.error("Missing required pattern parameter for grep operation")
                elif op_type == 'ls' and 'path' not in params:
                    logger.error("Missing required path parameter for ls operation")
            
            # Clean up parameter values - ensure no unwanted escape sequences
            for key in params:
                params[key] = params[key].strip()
                # Remove any \n escape sequences that may have been included literally in the string
                if '\\n' in params[key]:
                    params[key] = params[key].replace('\\n', '\n')
            
            # Log the parsed parameters for debugging
            logger.debug(f"Parsed file operation parameters: {params}")
            
            # Helper function to handle tilde expansion in paths
            def expand_path(path):
                if path and path.startswith("~"):
                    from pathlib import Path
                    home_dir = str(Path.home())
                    return home_dir + path[1:]
                return path
                
            # Execute the appropriate file operation with better error handling
            if op_type == "view":
                file_path = params.get("file_path")
                if not file_path:
                    print("Error: Missing required parameter 'file_path' for view operation")
                    return
                
                # Handle tilde expansion
                file_path = expand_path(file_path)
                    
                offset = 0
                limit = 2000
                try:
                    if "offset" in params:
                        offset = int(params["offset"])
                    if "limit" in params:
                        limit = int(params["limit"])
                except ValueError as e:
                    print(f"Error: Invalid offset or limit value: {e}")
                    return
                
                try:
                    result = await self.system_control.view_file(file_path, offset, limit)
                    line_count = len(result.splitlines())
                    print(f"📄 Viewed {file_path} ({line_count} lines)")
                    
                    # For large files, only show a preview
                    if line_count > 5 and limit > 10:
                        print("  ┌─────────────────────────────────────────────────────")
                        print(f"  │ First 3 lines of {file_path}:")
                        for line in result.splitlines()[:3]:
                            truncated = line[:80] + "..." if len(line) > 80 else line
                            print(f"  │ {truncated}")
                        print(f"  │ ... and {line_count - 3} more lines")
                        print("  └─────────────────────────────────────────────────────")
                    else:
                        print("  ┌─────────────────────────────────────────────────────")
                        for line in result.splitlines():
                            print(f"  │ {line}")
                        print("  └─────────────────────────────────────────────────────")
                    
                    # Return summary for auto-handling
                    return f"Viewed {file_path} ({line_count} lines)"
                except Exception as e:
                    error_msg = f"Error viewing file: {str(e)}"
                    print(f"❌ {error_msg}")
                    
                    # Try fallback to bash cat command
                    try:
                        print(f"🔄 Falling back to bash cat command...")
                        offset_arg = f"| tail -n +{offset+1}" if offset > 0 else ""
                        limit_arg = f"| head -n {limit}" if limit > 0 else ""
                        cmd = f"cat {file_path} {offset_arg} {limit_arg}"
                        stdout, stderr, code = await self.system_control.execute_command("bash", cmd)
                        if code == 0:
                            print(f"✅ Fallback successful using: {cmd}")
                            line_count = len(stdout.splitlines())
                            print("  ┌─────────────────────────────────────────────────────")
                            if line_count > 5:
                                for line in stdout.splitlines()[:5]:
                                    truncated = line[:80] + "..." if len(line) > 80 else line
                                    print(f"  │ {truncated}")
                                print(f"  │ ... and {line_count - 5} more lines")
                            else:
                                for line in stdout.splitlines():
                                    print(f"  │ {line}")
                            print("  └─────────────────────────────────────────────────────")
                            return f"Viewed {file_path} using fallback bash command ({line_count} lines)"
                        else:
                            return f"Error: {error_msg} (fallback also failed: {stderr})"
                    except Exception as fallback_error:
                        return f"Error: {error_msg} (fallback also failed: {str(fallback_error)})"
                
            elif op_type == "edit":
                file_path = params.get("file_path")
                if not file_path:
                    print("Error: Missing required parameter 'file_path' for edit operation")
                    return
                
                # Handle tilde expansion
                file_path = expand_path(file_path)
                
                # Get old_string and new_string parameters, ensuring we handle them carefully
                old_string = params.get("old_string", "")
                new_string = params.get("new_string", "")
                
                # Debug information to help diagnose issues
                logger.debug(f"Edit operation - File: {file_path}")
                logger.debug(f"Old string length: {len(old_string)}")
                logger.debug(f"New string length: {len(new_string)}")
                
                # Check that we're not processing file_path with & or other indicators of parsing issues
                if '&' in file_path or '\n' in file_path:
                    logger.error(f"Invalid file path detected: {file_path}")
                    return f"Error: Invalid file path - path contains special characters that suggest a parsing issue"
                
                try:
                    result = await self.system_control.edit_file(file_path, old_string, new_string)
                    
                    # Show a compact summary of the edit
                    if "successfully" in result.lower():
                        old_lines = old_string.count('\n') + 1
                        new_lines = new_string.count('\n') + 1
                        summary = f"Edited {file_path}: replaced {old_lines} line(s) with {new_lines} line(s)"
                        print(f"✏️ {summary}")
                        return summary
                    else:
                        error_msg = f"Edit failed: {result}"
                        print(f"❌ {error_msg}")
                        
                        # Try a fallback using temp file and sed if possible
                        try:
                            print(f"🔄 Falling back to bash commands for editing...")
                            
                            # Create a temp file for the edit
                            temp_file = f"/tmp/agent_edit_{os.path.basename(file_path)}.tmp"
                            
                            # Use different approaches based on whether file exists and old_string content
                            if not os.path.exists(file_path) and not old_string:
                                # Create new file directly
                                cmd = f"cat > {file_path} << 'EOF'\n{new_string}\nEOF"
                            elif not old_string:
                                # Replace entire file
                                cmd = f"cat > {file_path} << 'EOF'\n{new_string}\nEOF"
                            else:
                                # Create a sed script for the replacement
                                # We need to escape the strings for sed
                                escaped_old = old_string.replace("'", "'\\''").replace("/", "\\/")
                                escaped_new = new_string.replace("'", "'\\''").replace("/", "\\/")
                                
                                # Create a sed script that uses a different delimiter (|) to avoid issues
                                sed_script = f"s|{escaped_old}|{escaped_new}|"
                                cmd = f"sed -i '{sed_script}' {file_path}"
                            
                            stdout, stderr, code = await self.system_control.execute_command("bash", cmd)
                            
                            if code == 0:
                                print(f"✅ Fallback file edit successful")
                                
                                # Verify the change was made
                                if os.path.exists(file_path):
                                    # Check if the file now contains the new string
                                    file_content = await self.system_control.view_file(file_path)
                                    if new_string in file_content or not old_string:
                                        return f"Edited {file_path} using fallback bash commands"
                                return f"File edited using fallback bash commands, but verification was inconclusive"
                            else:
                                return f"Error: {error_msg} (fallback also failed: {stderr})"
                        except Exception as fallback_error:
                            logger.error(f"Error in fallback edit: {fallback_error}")
                            return f"Error: {error_msg} (fallback also failed: {str(fallback_error)})"
                except Exception as e:
                    error_msg = f"Error editing file: {str(e)}"
                    print(f"❌ {error_msg}")
                    return f"Error: {error_msg}"
                
            elif op_type == "replace":
                file_path = params.get("file_path")
                if not file_path:
                    print("Error: Missing required parameter 'file_path' for replace operation")
                    return
                
                # Handle tilde expansion
                file_path = expand_path(file_path)
                
                # Get content parameter, ensuring we handle it carefully
                content = params.get("content", "")
                
                # Debug information to help diagnose issues
                logger.debug(f"Replace operation - File: {file_path}")
                logger.debug(f"Content length: {len(content)}")
                
                # Check for invalid file paths
                if '&' in file_path or '\n' in file_path:
                    logger.error(f"Invalid file path detected: {file_path}")
                    return f"Error: Invalid file path - path contains special characters that suggest a parsing issue"
                line_count = content.count('\n') + 1
                
                try:
                    result = await self.system_control.replace_file(file_path, content)
                    
                    # Show a compact summary of the replacement
                    if "successfully" in result.lower():
                        summary = f"Replaced {file_path} with {line_count} lines of content"
                        print(f"💾 {summary}")
                        return summary
                    else:
                        error_msg = f"Replace failed: {result}"
                        print(f"❌ {error_msg}")
                        
                        # Try a fallback using bash
                        try:
                            print(f"🔄 Falling back to bash command for file replacement...")
                            
                            # Ensure the directory exists
                            dir_path = os.path.dirname(file_path)
                            if dir_path and not os.path.exists(dir_path):
                                mkdir_cmd = f"mkdir -p {dir_path}"
                                await self.system_control.execute_command("bash", mkdir_cmd)
                            
                            # Use heredoc to write the file content
                            cmd = f"cat > {file_path} << 'EOF'\n{content}\nEOF"
                            stdout, stderr, code = await self.system_control.execute_command("bash", cmd)
                            
                            if code == 0:
                                print(f"✅ Fallback file replacement successful")
                                return f"Replaced {file_path} with {line_count} lines using fallback bash command"
                            else:
                                return f"Error: {error_msg} (fallback also failed: {stderr})"
                        except Exception as fallback_error:
                            logger.error(f"Error in fallback replace: {fallback_error}")
                            return f"Error: {error_msg} (fallback also failed: {str(fallback_error)})"
                except Exception as e:
                    error_msg = f"Error replacing file: {str(e)}"
                    print(f"❌ {error_msg}")
                    return f"Error: {error_msg}"
                
            elif op_type == "glob":
                pattern = params.get("pattern")
                if not pattern:
                    print("Error: Missing required parameter 'pattern' for glob operation")
                    return
                    
                path = params.get("path")
                # Handle tilde expansion
                path = expand_path(path) if path else path
                
                try:
                    results = await self.system_control.glob_search(pattern, path)
                    result_count = len(results)
                    summary = f"Glob search for '{pattern}': found {result_count} file(s)"
                    print(f"🔍 {summary}")
                    
                    # Show compact results with better formatting
                    if result_count > 0:
                        # Display up to 10 results, with an indicator if there are more
                        print("  ┌─────────────────────────────────────────────────────")
                        max_display = min(10, result_count)
                        for i in range(max_display):
                            print(f"  │ {results[i]}")
                        if result_count > max_display:
                            print(f"  │ ...and {result_count - max_display} more files")
                        print("  └─────────────────────────────────────────────────────")
                except Exception as e:
                    error_msg = f"Error in glob search: {str(e)}"
                    print(f"❌ {error_msg}")
                    
                    # Try fallback to bash find or ls command
                    try:
                        print(f"🔄 Falling back to bash command...")
                        search_path = path if path else self.current_dir
                        search_path = search_path.rstrip('/')
                        
                        # Determine the appropriate bash command based on pattern
                        if '*' in pattern or '?' in pattern:
                            # Simple glob pattern - use ls
                            if pattern.startswith('**/'):
                                # Recursive pattern
                                cmd = f"find {search_path} -type f -name '{pattern.replace('**/', '')}' | sort"
                            else:
                                # Non-recursive pattern
                                cmd = f"ls -1 {search_path}/{pattern} 2>/dev/null || echo 'No matches found'"
                        else:
                            # No wildcards - just check if file exists
                            cmd = f"ls -1 {search_path}/{pattern} 2>/dev/null || echo 'No matches found'"
                        
                        stdout, stderr, code = await self.system_control.execute_command("bash", cmd)
                        
                        if code == 0 and stdout and 'No matches found' not in stdout:
                            print(f"✅ Fallback successful using: {cmd}")
                            results = stdout.strip().split('\n')
                            result_count = len(results)
                            
                            summary = f"Glob search for '{pattern}' (fallback): found {result_count} file(s)"
                            print(f"🔍 {summary}")
                            
                            if result_count > 0:
                                print("  ┌─────────────────────────────────────────────────────")
                                max_display = min(10, result_count)
                                for i in range(max_display):
                                    print(f"  │ {results[i]}")
                                if result_count > max_display:
                                    print(f"  │ ...and {result_count - max_display} more files")
                                print("  └─────────────────────────────────────────────────────")
                                
                                # Set results for return value
                                results = results
                            else:
                                print("  No files found matching the pattern")
                                results = []
                        else:
                            print(f"❌ Fallback search failed: {stderr}")
                            results = []
                    except Exception as fallback_error:
                        print(f"❌ Fallback error: {str(fallback_error)}")
                        return f"Error: {error_msg} (fallback also failed: {str(fallback_error)})"
                
                # Include first few results in the summary for auto-handling
                if result_count > 0:
                    result_summary = summary + "\n" + "\n".join(
                        [f"- {results[i]}" for i in range(min(5, result_count))]
                    )
                    if result_count > 5:
                        result_summary += f"\n- ... and {result_count - 5} more files"
                    return result_summary
                return summary
                
            elif op_type == "grep":
                pattern = params.get("pattern")
                if not pattern:
                    print("Error: Missing required parameter 'pattern' for grep operation")
                    return
                    
                include = params.get("include")
                path = params.get("path")
                # Handle tilde expansion
                path = expand_path(path) if path else path
                
                results = await self.system_control.grep_search(pattern, include, path)
                result_count = len(results)
                include_str = f" in '{include}' files" if include else ""
                summary = f"Grep search for '{pattern}'{include_str}: {result_count} match(es)"
                print(f"🔍 {summary}")
                
                # Group by file for display and summary
                files = {}
                for result in results:
                    file_path = result['file']
                    if file_path not in files:
                        files[file_path] = []
                    files[file_path].append((result['line_number'], result['line']))
                
                # Show compact results
                if result_count > 0:
                    # Display up to 5 files
                    file_count = len(files)
                    displayed_files = 0
                    for file_path, matches in files.items():
                        if displayed_files >= 5:
                            break
                        displayed_files += 1
                        match_count = len(matches)
                        print(f"  📄 {file_path} ({match_count} match(es))")
                        
                        # Display up to 3 matches per file
                        for i, (line_num, line) in enumerate(matches[:3]):
                            # Truncate long lines
                            if len(line) > 60:
                                line = line[:57] + "..."
                            print(f"    {line_num}: {line}")
                        
                        if match_count > 3:
                            print(f"    ...and {match_count - 3} more matches")
                    
                    if file_count > 5:
                        print(f"  ...and matches in {file_count - 5} more files")
                
                # Create summary for auto-handling
                if result_count > 0:
                    result_summary = summary + "\n"
                    file_summaries = []
                    for i, (file_path, matches) in enumerate(files.items()):
                        if i >= 3:  # Limit to 3 files in summary
                            break
                        match_previews = []
                        for j, (line_num, line) in enumerate(matches[:2]):  # Limit to 2 matches per file
                            # Limit line length
                            preview = line[:50] + "..." if len(line) > 50 else line
                            match_previews.append(f"  Line {line_num}: {preview}")
                        
                        file_summary = f"- {file_path} ({len(matches)} match(es)):\n" + "\n".join(match_previews)
                        if len(matches) > 2:
                            file_summary += f"\n  ... and {len(matches) - 2} more matches"
                        file_summaries.append(file_summary)
                        
                    result_summary += "\n".join(file_summaries)
                    if len(files) > 3:
                        result_summary += f"\n\n... and matches in {len(files) - 3} more files"
                    return result_summary
                    
                return summary
                
            elif op_type == "ls":
                path = params.get("path")
                if not path:
                    print("Error: Missing required parameter 'path' for ls operation")
                    return
                
                # Handle tilde expansion
                path = expand_path(path)
                
                # Get hide_hidden parameter (default is False - show hidden files)
                hide_hidden_param = params.get("hide_hidden", "false").lower()
                hide_hidden = hide_hidden_param in ["true", "yes", "1"]
                
                try:
                    # Pass the hide_hidden parameter (by default we show hidden files)
                    result = await self.system_control.list_directory(path, hide_hidden)
                    item_count = len(result["entries"])
                    dir_count = sum(1 for item in result["entries"] if item["is_dir"])
                    file_count = item_count - dir_count
                    
                    summary = f"Directory '{path}': {dir_count} directories, {file_count} files"
                    print(f"📂 {summary}")
                    
                    # Count special types
                    hidden_count = sum(1 for item in result["entries"] if item["name"].startswith("."))
                    
                    if item_count > 0:
                        # Group by type (directories first)
                        dirs = [item for item in result["entries"] if item["is_dir"]]
                        files = [item for item in result["entries"] if not item["is_dir"]]
                        
                        # Sort alphabetically
                        dirs.sort(key=lambda x: x["name"])
                        files.sort(key=lambda x: x["name"])
                        
                        # Display up to 5 directories
                        if dirs:
                            if len(dirs) <= 5:
                                for item in dirs:
                                    print(f"  📁 {item['name']}/")
                            else:
                                for item in dirs[:5]:
                                    print(f"  📁 {item['name']}/")
                                print(f"  ...and {len(dirs) - 5} more directories")
                        
                        # Display up to 5 files
                        if files:
                            if len(files) <= 5:
                                for item in files:
                                    print(f"  📄 {item['name']}")
                            else:
                                for item in files[:5]:
                                    print(f"  📄 {item['name']}")
                                print(f"  ...and {len(files) - 5} more files")
                        
                        # Special note for hidden files
                        if hidden_count > 0:
                            print(f"  ({hidden_count} hidden items)")
                        
                        # Create detailed summary for auto-handling
                        result_summary = summary + "\n"
                        
                        # Add directories to summary
                        if dirs:
                            result_summary += "\nDirectories:\n"
                            for item in dirs[:min(5, len(dirs))]:
                                result_summary += f"- {item['name']}/\n"
                            if len(dirs) > 5:
                                result_summary += f"- ... and {len(dirs) - 5} more directories\n"
                        
                        # Add files to summary
                        if files:
                            result_summary += "\nFiles:\n"
                            for item in files[:min(5, len(files))]:
                                result_summary += f"- {item['name']}\n"
                            if len(files) > 5:
                                result_summary += f"- ... and {len(files) - 5} more files\n"
                        
                        return result_summary
                    
                    return summary
                except Exception as e:
                    error_msg = f"Error listing directory: {str(e)}"
                    print(f"❌ {error_msg}")
                    
                    # Try fallback to bash ls command
                    try:
                        print(f"🔄 Falling back to bash ls command...")
                        cmd = f"ls -la {abs_path}"
                        stdout, stderr, code = await self.shell_adapter.execute_command(cmd)
                        if code == 0:
                            print(f"✅ Fallback successful using: {cmd}")
                            return {
                                "path": abs_path,
                                "fallback_output": stdout,
                                "fallback_used": True,
                                "original_error": str(e)
                            }
                        else:
                            return f"Error: {error_msg} (fallback also failed: {stderr})"
                    except Exception as fallback_error:
                        return f"Error: {error_msg} (fallback also failed: {str(fallback_error)})"
                    
        except Exception as e:
            logger.error(f"Error processing file operation {op_type}: {e}")
            print(f"\n[ERROR] Error processing file operation: {str(e)}")
            
    async def _get_user_input(self) -> str:
        """
        Get input from the user with command history support.
        Uses readline for history if available.
        """
        self.agent_state['status'] = 'waiting_for_input'
        
        # Configure readline for history if it's available
        try:
            import readline
            import os
            
            # Check if readline is already configured (avoid duplicate setup)
            if not hasattr(self, '_readline_initialized'):
                # Setup readline with history file
                history_file = os.path.expanduser('~/.agent_history')
                try:
                    readline.read_history_file(history_file)
                    readline.set_history_length(1000)
                except FileNotFoundError:
                    pass
                
                # Save history on exit
                import atexit
                atexit.register(readline.write_history_file, history_file)
                
                # Mark as initialized to avoid redoing setup
                self._readline_initialized = True
        except (ImportError, ModuleNotFoundError):
            # Readline not available, continue without it
            pass
        
        try:
            # Clear any pending input buffer before showing prompt
            import sys
            
            # Import termios first to avoid referring to a module that might not exist
            try:
                import termios
                import tty
                has_termios = True
            except (ImportError, ModuleNotFoundError):
                has_termios = False
            
            # Check if we're in an interactive TTY and termios is available
            if sys.stdin.isatty() and has_termios:
                fd = sys.stdin.fileno()
                try:
                    old_settings = termios.tcgetattr(fd)
                    try:
                        tty.setraw(fd)
                        # Just check if there's input waiting but don't block
                        ready_to_read = select.select([sys.stdin], [], [], 0)[0]
                        if ready_to_read:
                            # Clear pending input
                            os.read(fd, 1024)
                    finally:
                        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except termios.error:
                    # Terminal doesn't support termios operations
                    pass
            else:
                # Not connected to a TTY, skip terminal operations
                pass
        except (AttributeError, IOError):
            # Not on Unix or terminal doesn't support these operations
            pass
        
        # Show a clear, visible prompt
        prompt = "\n[User Input] > "
        print(prompt, end="", flush=True)
        
        # Visual indicator that input is being processed
        def input_with_feedback():
            try:
                result = input()
                return result
            except EOFError:
                return ""
            
        # Get input with asyncio to allow for other tasks
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input_with_feedback)
        
        # Visual feedback that input was received
        print(f"\n[Input received] Processing...", flush=True)
        
        self.agent_state['status'] = 'running'
        return user_input
    
    async def _compact_conversation(self) -> None:
        """Compact the conversation to save context space"""
        if len(self.local_conversation_history) <= 2:
            print("\nConversation is already compact.")
            return
            
        # Keep system prompt and initial user prompt
        system_prompt = self.local_conversation_history[0]["content"]
        
        # Find the first user prompt
        initial_prompt = ""
        for msg in self.local_conversation_history:
            if msg["role"] == "user":
                initial_prompt = msg["content"]
                break
        
        # Keep the last few exchanges for context
        last_entries = self.local_conversation_history[-4:] if len(self.local_conversation_history) >= 4 else self.local_conversation_history
        
        # Create a summary of what was discussed
        summary = "Previous conversation summary:\n\n"
        
        # Add a summary of commands executed
        commands_executed = [msg for msg in self.local_conversation_history if msg["role"] == "assistant"]
        command_summary = []
        for msg in commands_executed:
            commands = self.command_extractor.extract_commands(msg["content"])
            if commands:
                for cmd_type, cmd in commands:
                    cmd_preview = cmd.split('\n')[0][:40] + ('...' if len(cmd) > 40 else '')
                    command_summary.append(f"- {cmd_type}: {cmd_preview}")
        
        if command_summary:
            summary += "Commands executed:\n" + "\n".join(command_summary[:10])
            if len(command_summary) > 10:
                summary += f"\n...and {len(command_summary) - 10} more commands."
            summary += "\n\n"
        
        # Create new compact history with only system prompt and initial user prompt
        self.local_conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_prompt},
            {"role": "assistant", "content": "Initial task completed. Here's a summary of what was done:\n\n" + summary},
            {"role": "user", "content": "Continue with the next steps based on the previous work."}
        ]
        
        # Add the last exchange for immediate context
        if last_entries and len(last_entries) >= 2:
            self.local_conversation_history.append(last_entries[-2])  # Last user message
            self.local_conversation_history.append(last_entries[-1])  # Last assistant message
        
        print("\nConversation compacted to keep initial prompt and latest context only.")
        
    async def _save_session_summary(self) -> None:
        """Save a summary of the current session"""
        try:
            summary_path = self.memory_path / "summaries"
            summary_path.mkdir(exist_ok=True, parents=True)
            
            # Extract summary from conversation
            user_queries = [msg["content"] for msg in self.local_conversation_history if msg["role"] == "user"]
            assistant_responses = [msg["content"] for msg in self.local_conversation_history if msg["role"] == "assistant"]
            
            # Create a summary
            summary = f"Session Summary ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
            summary += "=" * 50 + "\n\n"
            
            if user_queries:
                summary += "Main queries:\n"
                for i, query in enumerate(user_queries[:3], 1):
                    preview = query[:100] + ('...' if len(query) > 100 else '')
                    summary += f"{i}. {preview}\n"
                
                if len(user_queries) > 3:
                    summary += f"...and {len(user_queries) - 3} more queries.\n"
                summary += "\n"
            
            # Add command summary
            commands = []
            for response in assistant_responses:
                extracted = self.command_extractor.extract_commands(response)
                commands.extend(extracted)
            
            if commands:
                summary += f"Commands executed: {len(commands)}\n"
                for i, (cmd_type, cmd) in enumerate(commands[:5], 1):
                    preview = cmd.split('\n')[0][:40] + ('...' if len(cmd) > 40 else '')
                    summary += f"{i}. {cmd_type}: {preview}\n"
                
                if len(commands) > 5:
                    summary += f"...and {len(commands) - 5} more commands.\n"
                summary += "\n"
                
            # Add thinking/planning summary if available
            thinking = []
            for response in assistant_responses:
                extracted = self.command_extractor.extract_thinking(response)
                thinking.extend(extracted)
            
            if thinking:
                summary += "Key insights:\n"
                for i, thought in enumerate(thinking[:3], 1):
                    preview = thought[:100] + ('...' if len(thought) > 100 else '')
                    summary += f"{i}. {preview}\n"
                summary += "\n"
            
            # Save the summary
            timestamp = int(time.time())
            with open(summary_path / f"{timestamp}_summary.txt", "w") as f:
                f.write(summary)
                
            # Also save as last_session.txt
            with open(summary_path / "last_session.txt", "w") as f:
                f.write(summary)
                
            # Save session conversation to memory
            if self.memory_manager and self.current_conversation_id:
                self.memory_manager.save_conversation(
                    self.current_conversation_id,
                    self.local_conversation_history,
                    metadata={
                        "commands_executed": self.agent_state['commands_executed'],
                        "status": "completed",
                        "timestamp": timestamp
                    }
                )
            
            logger.info(f"Session summary saved to {summary_path}/last_session.txt")
            
        except Exception as e:
            logger.error(f"Error saving session summary: {e}")
            
    async def add_human_context(self, context_text: str) -> None:
        """Add human-provided context to the conversation"""
        if self.last_assistant_response:
            # Add a marker in the conversation history
            context_marker = f"\n\n[HUMAN_ADDED_CONTEXT]\n{context_text}\n[/HUMAN_ADDED_CONTEXT]\n\n"
            
            # Update the last assistant response
            last_msg_index = None
            for i, msg in enumerate(self.local_conversation_history):
                if msg["role"] == "assistant":
                    last_msg_index = i
                    
            if last_msg_index is not None:
                original_content = self.local_conversation_history[last_msg_index]["content"]
                modified_content = original_content + context_marker
                self.local_conversation_history[last_msg_index]["content"] = modified_content
                
                # Update the saved last response
                self.last_assistant_response = modified_content
                self.paused_for_human_context = True
