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
                
                # Extract commands and plan steps from the response
                should_continue = await self._process_response(response)
                
                if should_continue and not self.should_exit:
                    # Get user input for the next turn
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
                            print("\nAvailable slash commands:")
                            print("  /help     - Show this help message")
                            print("  /compact  - Compact conversation history to save context space")
                            print("  /pause    - Same as pressing Ctrl+Z, pause to add context")
                            user_input = "The user requested help with slash commands. I showed them the available commands. Please continue."
                    
                    # Generate the next response
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
            # Extract commands
            commands = self.command_extractor.extract_commands(response)
            
            # Extract user input requests
            input_requests = self.command_extractor.extract_user_input_requests(response)
            
            # Process user input requests first
            if input_requests:
                print("\n" + "=" * 60)
                print("AGENT REQUESTING INPUT")
                print("-" * 60)
                print(input_requests[0])  # Take the first input request
                print("=" * 60 + "\n")
                
                # Get user input
                user_input = await self._get_user_input()
                
                # Add the input to the conversation
                self.local_conversation_history.append({
                    "role": "user",
                    "content": user_input
                })
                
                # Generate new response with the input
                new_response = await self._generate_response(None, user_input)
                
                # Process the new response
                return await self._process_response(new_response)
            
            # Process commands
            for cmd_type, command in commands:
                if self.command_extractor.is_exit_command(cmd_type, command):
                    self.should_exit = True
                    return False
                
                # Process file operations
                if cmd_type in self.command_extractor.FILE_OP_TAGS:
                    await self._process_file_operation(cmd_type, command)
                    continue
                
                # Process bash or python commands
                if cmd_type in ["bash", "python"]:
                    stdout, stderr, code = await self.system_control.execute_command(cmd_type, command)
                    self.agent_state['commands_executed'] += 1
                    self.agent_state['last_active'] = datetime.now().isoformat()
                    
                    # Record command in history
                    self.command_history.append({
                        "command": command,
                        "type": cmd_type,
                        "timestamp": time.time(),
                        "success": code == 0
                    })
                    
                    # Add the result to memory
                    if self.memory_manager:
                        self.memory_manager.add_command_to_history(command, cmd_type, code == 0)
            
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
            
    async def _process_file_operation(self, op_type: str, command: str) -> None:
        """Process file operations extracted from the response"""
        try:
            # Parse command parameters
            params = {}
            for line in command.strip().split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    params[key.strip()] = value.strip()
            
            # Execute the appropriate file operation
            if op_type == "view":
                file_path = params.get("file_path")
                offset = int(params.get("offset", "0"))
                limit = int(params.get("limit", "2000"))
                
                if file_path:
                    result = await self.system_control.view_file(file_path, offset, limit)
                    print(f"\nContents of {file_path}:\n")
                    print(result)
                    
            elif op_type == "edit":
                file_path = params.get("file_path")
                old_string = params.get("old_string", "")
                new_string = params.get("new_string", "")
                
                if file_path:
                    result = await self.system_control.edit_file(file_path, old_string, new_string)
                    print(f"\nEdit result for {file_path}:\n")
                    print(result)
                    
            elif op_type == "replace":
                file_path = params.get("file_path")
                content = params.get("content", "")
                
                if file_path:
                    result = await self.system_control.replace_file(file_path, content)
                    print(f"\nReplace result for {file_path}:\n")
                    print(result)
                    
            elif op_type == "glob":
                pattern = params.get("pattern")
                path = params.get("path")
                
                if pattern:
                    results = await self.system_control.glob_search(pattern, path)
                    print(f"\nGlob search results for pattern '{pattern}':\n")
                    for result in results:
                        print(result)
                        
            elif op_type == "grep":
                pattern = params.get("pattern")
                include = params.get("include")
                path = params.get("path")
                
                if pattern:
                    results = await self.system_control.grep_search(pattern, include, path)
                    print(f"\nGrep search results for pattern '{pattern}':\n")
                    for result in results:
                        print(f"{result['file']}:{result['line_number']}: {result['line']}")
                        
            elif op_type == "ls":
                path = params.get("path")
                
                if path:
                    result = await self.system_control.list_directory(path)
                    print(f"\nDirectory listing for {path}:\n")
                    for item in result["entries"]:
                        item_type = "d" if item["is_dir"] else "f"
                        print(f"{item_type} {item['name']}")
                        
        except Exception as e:
            logger.error(f"Error processing file operation {op_type}: {e}")
            print(f"\nError processing file operation: {str(e)}")
            
    async def _get_user_input(self) -> str:
        """Get input from the user"""
        self.agent_state['status'] = 'waiting_for_input'
        prompt = " > "
        print(prompt, end="", flush=True)
        
        # Get input with asyncio to allow for other tasks
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input)
        
        self.agent_state['status'] = 'running'
        return user_input
    
    async def _compact_conversation(self) -> None:
        """Compact the conversation to save context space"""
        if len(self.local_conversation_history) <= 2:
            print("\nConversation is already compact.")
            return
            
        # Keep system prompt and last few exchanges
        system_prompt = self.local_conversation_history[0]["content"]
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
        
        # Create new compact history
        self.local_conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": summary}
        ]
        
        # Add the last few exchanges
        for entry in last_entries:
            if entry["role"] != "system":  # Skip system prompt as we already added it
                self.local_conversation_history.append(entry)
                
        print("\nConversation compacted to save context space.")
        
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
