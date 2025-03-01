import asyncio
import logging
import os
import json
import re
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Set, Union

from core.llm_client import get_llm_client
from core.memory_manager import MemoryManager
from core.system_control import SystemControl
from core.task_manager import TaskManager
from core.session_manager import SessionManager
import networkx as nx

logger = logging.getLogger(__name__)

class CommandResult:
    """Enhanced command execution results"""
    def __init__(self, stdout: str, stderr: str, code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.code = code
        self.success = code == 0
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
    """Extracts commands from LLM responses using XML tags"""
    
    COMMAND_TAGS = ['bash', 'python']
    THINKING_TAG = 'thinking'
    DECISION_TAG = 'decision'
    PLAN_TAG = 'plan'
    SUMMARY_TAG = 'summary'
    TASK_TAG = 'task'  # New tag for long-term task planning
    SUBTASK_TAG = 'subtask'  # New tag for breaking down tasks into smaller components
    
    # File operation tags
    FILE_OP_TAGS = ['view', 'edit', 'replace', 'glob', 'grep', 'ls']
    
    # User input tag
    USER_INPUT_TAG = 'user_input'  # For extracting user input requests
    
    @staticmethod
    def extract_commands(response: str) -> List[Tuple[str, str]]:
        """Extract commands from response with robust pattern matching"""
        commands = []
        
        # Process standard command tags (bash, python)
        CommandExtractor._extract_tag_commands(response, CommandExtractor.COMMAND_TAGS, commands)
        
        # Process file operation tags
        CommandExtractor._extract_tag_commands(response, CommandExtractor.FILE_OP_TAGS, commands)
                            
        return commands
        
    @staticmethod
    def _extract_tag_commands(response: str, tags: List[str], commands: List[Tuple[str, str]]) -> None:
        """Extract commands for a set of tags and add them to the commands list"""
        # Match with more flexible regex that handles malformed XML better
        for tag in tags:
            # Try strict matching first
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, response, re.DOTALL)
            strict_matches = list(matches)
            
            if strict_matches:
                for match in strict_matches:
                    command = match.group(1).strip()
                    if command:
                        commands.append((tag, command))
            else:
                # Try more lenient matching as fallback
                open_tag_pattern = f"<{tag}>"
                close_tag_pattern = f"</{tag}>"
                
                # Find all start positions
                starts = [m.end() for m in re.finditer(open_tag_pattern, response)]
                # Find all end positions
                ends = [m.start() for m in re.finditer(close_tag_pattern, response)]
                
                # Match starts with their closest end position
                for start in starts:
                    valid_ends = [e for e in ends if e > start]
                    if valid_ends:
                        end = min(valid_ends)  # Get closest end tag
                        command = response[start:end].strip()
                        if command:
                            commands.append((tag, command))
    
    @staticmethod
    def extract_thinking(response: str) -> List[str]:
        """Extract thinking blocks from response"""
        return CommandExtractor._extract_tag_content(response, CommandExtractor.THINKING_TAG)
    
    @staticmethod
    def extract_decision(response: str) -> List[str]:
        """Extract decision blocks from response"""
        return CommandExtractor._extract_tag_content(response, CommandExtractor.DECISION_TAG)
    
    @staticmethod
    def extract_plan(response: str) -> List[str]:
        """Extract plan blocks from response"""
        return CommandExtractor._extract_tag_content(response, CommandExtractor.PLAN_TAG)
        
    @staticmethod
    def extract_summary(response: str) -> List[str]:
        """Extract summary blocks from response"""
        return CommandExtractor._extract_tag_content(response, CommandExtractor.SUMMARY_TAG)
        
    @staticmethod
    def extract_tasks(response: str) -> List[str]:
        """Extract task blocks from response for long-term planning"""
        return CommandExtractor._extract_tag_content(response, CommandExtractor.TASK_TAG)
        
    @staticmethod
    def extract_subtasks(response: str) -> List[str]:
        """Extract subtask blocks from response for task breakdown"""
        return CommandExtractor._extract_tag_content(response, CommandExtractor.SUBTASK_TAG)
        
    @staticmethod
    def extract_user_input_requests(response: str) -> List[str]:
        """Extract user input request blocks"""
        # Get standard tag format
        standard_requests = CommandExtractor._extract_tag_content(response, CommandExtractor.USER_INPUT_TAG)
        
        # Also try alternative formats for flexibility
        alt_pattern = r"\[PAUSE_FOR_USER_INPUT\](.*?)\[/PAUSE_FOR_USER_INPUT\]"
        alt_matches = re.finditer(alt_pattern, response, re.DOTALL)
        alt_requests = [match.group(1).strip() for match in alt_matches]
        
        # Combine all formats
        return standard_requests + alt_requests
        
    @staticmethod
    def _extract_tag_content(response: str, tag: str) -> List[str]:
        """Extract content from any XML-style tag with fallback for malformed tags"""
        # Try strict matching first
        pattern = f"<{tag}>(.*?)</{tag}>"
        matches = re.finditer(pattern, response, re.DOTALL)
        results = [match.group(1).strip() for match in matches]
        
        if not results:
            # Try more lenient matching as fallback
            open_tag_pattern = f"<{tag}>"
            close_tag_pattern = f"</{tag}>"
            
            # Find all start positions
            starts = [m.end() for m in re.finditer(open_tag_pattern, response)]
            # Find all end positions
            ends = [m.start() for m in re.finditer(close_tag_pattern, response)]
            
            # Match starts with their closest end position
            for start in starts:
                valid_ends = [e for e in ends if e > start]
                if valid_ends:
                    end = min(valid_ends)  # Get closest end tag
                    content = response[start:end].strip()
                    if content:
                        results.append(content)
        
        return results

    @staticmethod
    def extract_heredocs(response: str) -> List[Dict[str, str]]:
        """Extract heredoc blocks from response text with enhanced pattern matching"""
        heredocs = []
        
        # First try with regex pattern matching
        heredoc_pattern = r'cat\s*<<\s*EOF\s*>\s*([^\n]+)(.*?)EOF'
        matches = re.finditer(heredoc_pattern, response, re.DOTALL)
        for match in matches:
            filename = match.group(1).strip()
            content = match.group(2)
            heredocs.append({
                'filename': filename,
                'content': content
            })
            
        # If no matches, fall back to line-by-line parsing
        if not heredocs:
            current_doc = None
            content_lines = []
            
            for line in response.split('\n'):
                if not current_doc and ('cat << EOF >' in line or 'cat <<EOF >' in line):
                    # Extract filename accounting for different spacings
                    parts = line.strip().split('>')
                    if len(parts) > 1:
                        current_doc = parts[1].strip()
                        continue
                        
                elif line.strip() == 'EOF' and current_doc:
                    # End current heredoc
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
        """
        Check if command is an exit command. 
        We'll accept "exit", "quit", "bye", "done" (bash or python).
        """
        lower_cmd = command.strip().lower()
        exit_cmds = {"exit", "quit", "bye", "done"}
        
        # Check for direct matches
        if lower_cmd in exit_cmds:
            return True
            
        # Check for exit commands with arguments (e.g., "exit 0")
        for exit_cmd in exit_cmds:
            if lower_cmd.startswith(f"{exit_cmd} "):
                return True
                
        return False


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

        self.memory_path = Path("memory")
        self._setup_storage()

        self.memory_manager = memory_manager or MemoryManager()
        self.system_control = SystemControl(test_mode=test_mode)
        self.task_manager = TaskManager(self.memory_path)
        self.session_manager = session_manager or SessionManager(self.memory_path, self.memory_manager)

        # Agent identity and state tracking
        self.agent_id = str(uuid.uuid4())[:8]  # Generate unique agent ID
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

        # Seed memory if vector_index doesn't exist
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
                    # Also save agent identity
                    self.memory_manager.save_document(
                        "agent_identity",
                        f"Agent ID: {self.agent_id}\nInitialized: {self.agent_state['started_at']}\nModel: {model}",
                        tags=["system", "identity", "permanent"],
                        permanent=True
                    )
            except Exception as e:
                logger.error(f"Error seeding memory: {e}")

        # Initialize planning and introspection
        self.reflections = []
        self.planned_steps = []
        self.executive_summary = ""
        
        # Initialize LLM client
        self.llm = get_llm_client(model, api_key)
        self.model_name = model
        
        # Load previous state
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.command_extractor = CommandExtractor()
        self.should_exit = False
        self.command_history = []
        
        # Background tasks
        self.heartbeat_task = None
        self.resource_monitor_task = None
        self.test_mode = test_mode

        # Local conversation history for multi-turn dialogues
        # Each element is a dict like: {"role": "user"/"assistant"/"system", "content": "..."}
        self.local_conversation_history: List[Dict[str, str]] = []
        
        # Track working memory items (easily accessible memory for ongoing tasks)
        self.working_memory: Dict[str, Any] = {}
        
        # Update agent state
        self.agent_state['status'] = 'ready'

    async def run(self, initial_prompt: str, system_prompt: str) -> None:
        """
        Run the agent in a multi-turn conversation loop:
        1. We create a session
        2. Provide system prompt + initial prompt
        3. The agent responds with commands
        4. We execute them and return the output as the next user message
        5. Repeat until the agent triggers an exit command or completes the session
        """
        try:
            # Update agent state
            self.agent_state['status'] = 'running'
            self.agent_state['current_task'] = initial_prompt[:100] + ("..." if len(initial_prompt) > 100 else "")
            self.agent_state['last_active'] = datetime.now().isoformat()
            
            print("\nInitializing new session...")
            
            # Start background tasks
            self.heartbeat_task = asyncio.create_task(self.heartbeat())
            self.resource_monitor_task = asyncio.create_task(self._monitor_resources())

            # Record session start in memory
            session_id = f"{int(time.time())}_{self.agent_id}"
            self.memory_manager.save_document(
                f"session_start_{session_id}",
                f"Session started at {datetime.now().isoformat()}\nInitial task: {initial_prompt}",
                tags=["session", "meta", "start"],
                metadata={
                    "session_id": session_id,
                    "model": self.model_name,
                    "agent_id": self.agent_id
                }
            )

            # Start a new session in session manager
            env = dict(os.environ)
            working_dir = str(Path.cwd())
            self.session_manager.start_session(
                shell_preference="bash",
                working_directory=working_dir,
                environment=env,
                session_id=session_id
            )

            # Save the working directory to working memory
            self.working_memory['working_directory'] = working_dir
            self.working_memory['session_id'] = session_id

            # Add system message with additional context
            enhanced_system_prompt = self._enhance_system_prompt(system_prompt)
            system_msg = {"role": "system", "content": enhanced_system_prompt}
            self.local_conversation_history.append(system_msg)

            # Add initial user message (the "task" given)
            user_msg = {"role": "user", "content": initial_prompt}
            self.local_conversation_history.append(user_msg)

            # Initialize failure tracking
            consecutive_failures = 0
            max_failures = 3
            
            # Record task initiation in memory for long-term recordkeeping
            self.memory_manager.save_document(
                f"task_{session_id}",
                initial_prompt,
                tags=["task", "user_request"],
                metadata={"session_id": session_id, "status": "started"}
            )
            
            # Multi-turn loop
            turn_count = 0
            while not self.should_exit:
                turn_count += 1
                turn_start_time = time.time()
                try:
                    # Update agent state
                    self.agent_state['last_active'] = datetime.now().isoformat()
                    self.agent_state['turn_count'] = turn_count
                    
                    # Compress context if needed
                    compressed_history = await self.compress_context(self.local_conversation_history)
                    
                    # Record current working memory state for continuity
                    await self._save_working_memory_state()
                    
                    # Get LLM response (assistant message) with timeout
                    try:
                        # Apply a timeout to the LLM call to prevent hanging
                        llm_timeout = 120  # 2 minutes timeout for LLM calls
                        response = await asyncio.wait_for(
                            self.llm.get_response(
                                prompt=None,
                                system=None,
                                conversation_history=compressed_history,
                                tool_usage=False
                            ),
                            timeout=llm_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"LLM response timed out after {llm_timeout} seconds")
                        # Create a special error response
                        response = "I apologize, but my response was taking too long to generate. " + \
                                  "Let me try a simpler approach. Please give me a moment to reconsider."
                    
                    # Handle empty response
                    if not response:
                        logger.warning("No response from LLM.")
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            error_msg = f"Too many consecutive failures ({max_failures}). Ending session."
                            print(error_msg)
                            # Record the failure in memory
                            self.memory_manager.save_document(
                                f"error_{session_id}_{int(time.time())}",
                                error_msg,
                                tags=["error", "consecutive_failures"],
                                metadata={"session_id": session_id, "turn": turn_count}
                            )
                            break
                        continue
                    
                    # Reset failure counter on success
                    consecutive_failures = 0

                    # Store assistant message
                    assistant_msg = {"role": "assistant", "content": response}
                    self.local_conversation_history.append(assistant_msg)
                    self._print_response(response)
                    
                    # Check if the model is requesting user input
                    should_pause, question = await self.llm.check_for_user_input_request(response)
                    if should_pause:
                        # Handle user input request
                        user_input = await self._request_user_input(question)
                        
                        # Add user's response to conversation history
                        user_input_msg = {
                            "role": "user",
                            "content": f"You asked: {question}\n\nMy response: {user_input}"
                        }
                        self.local_conversation_history.append(user_input_msg)
                        
                        # Skip the rest of this iteration and continue with the updated conversation
                        continue

                    # Process reasoning blocks
                    await self._process_reasoning_blocks(response, session_id, turn_count)

                    # Process potential heredocs (file creation)
                    await self.process_heredocs(response)

                    # Extract commands
                    commands = self.command_extractor.extract_commands(response)
                    
                    # Handle case where no commands were found
                    if not commands:
                        await self._handle_no_commands(response, session_id, turn_count)
                        continue

                    # Execute commands and process outputs
                    all_outputs = await self._execute_commands(commands, session_id, turn_count)
                    
                    # Check if agent decided to exit during command execution
                    if self.should_exit:
                        break
                        
                    # Provide command outputs as the next user message
                    if all_outputs:
                        combined_message = "\n\n".join(all_outputs)
                        next_user_msg = {
                            "role": "user",
                            "content": combined_message
                        }
                        self.local_conversation_history.append(next_user_msg)
                        
                        # Create periodic backups during the session
                        if turn_count % 5 == 0:  # Every 5 turns
                            self.memory_manager.create_backup()
                            
                    # Record turn duration for performance monitoring
                    turn_duration = time.time() - turn_start_time
                    logger.info(f"Turn {turn_count} completed in {turn_duration:.2f}s")
                    
                    # Add performance data to working memory
                    if 'performance' not in self.working_memory:
                        self.working_memory['performance'] = []
                    self.working_memory['performance'].append({
                        'turn': turn_count,
                        'duration': turn_duration,
                        'timestamp': time.time(),
                        'commands_executed': len(commands) if commands else 0
                    })
                    
                except Exception as turn_error:
                    logger.error(f"Error during conversation turn: {turn_error}")
                    consecutive_failures += 1
                    
                    # Record the error in memory
                    error_msg = f"Error during turn {turn_count}: {str(turn_error)}"
                    self.agent_state['last_error'] = error_msg
                    self.memory_manager.save_document(
                        f"error_{session_id}_{int(time.time())}",
                        error_msg,
                        tags=["error", "turn_failure"],
                        metadata={"session_id": session_id, "turn": turn_count, "error": str(turn_error)}
                    )
                    
                    # Attempt recovery
                    try:
                        # Notify the agent about the error
                        error_msg = {
                            "role": "user", 
                            "content": f"An error occurred: {str(turn_error)}. Please continue with a different approach."
                        }
                        self.local_conversation_history.append(error_msg)
                        
                        # If we've had too many consecutive failures, exit
                        if consecutive_failures >= max_failures:
                            print(f"Too many consecutive failures ({max_failures}). Ending session.")
                            break
                    except Exception as recovery_error:
                        logger.error(f"Error during error recovery: {recovery_error}")
                        # If recovery itself fails, we have to exit
                        break

            # Session end handling
            if self.should_exit:
                print("\nSession ended by agent.")
            else:
                print("\nSession completed naturally or stopped due to errors.")
                
            # Record session completion in memory
            self.memory_manager.save_document(
                f"session_end_{session_id}",
                f"Session ended at {datetime.now().isoformat()}\nTurns: {turn_count}\nExit requested: {self.should_exit}",
                tags=["session", "meta", "end"],
                metadata={
                    "session_id": session_id,
                    "turns": turn_count,
                    "requested_exit": self.should_exit,
                    "duration": (datetime.now() - datetime.fromisoformat(self.agent_state['started_at'])).total_seconds()
                }
            )
            
            # Generate and save final reflection
            await self._generate_final_reflection(session_id, turn_count)

        except Exception as e:
            logger.error(f"Run failed: {e}")
            # Save state before exiting
            self.memory_manager.create_backup(force=True)
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise
        finally:
            print("\nCleaning up...")
            # Update agent state
            self.agent_state['status'] = 'inactive'
            self.agent_state['last_active'] = datetime.now().isoformat()
            
            # Cancel background tasks
            for task_name, task in [
                ("heartbeat", self.heartbeat_task),
                ("resource_monitor", self.resource_monitor_task)
            ]:
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.debug(f"{task_name} task canceled")
                        
            # Final cleanup
            self.cleanup()

    async def process_heredocs(self, response: str) -> List[str]:
        """
        Process and save heredoc content to files
        
        Returns:
            List of created file paths
        """
        heredocs = self.command_extractor.extract_heredocs(response)
        created_files = []
        
        for doc in heredocs:
            try:
                filepath = Path(doc['filename'])
                
                # No safety restrictions - allow writing to any directory
                # Security restrictions removed as requested
                
                # Create parent directory if needed
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                # Write the file
                with open(filepath, 'w') as f:
                    f.write(doc['content'])
                    
                logger.info(f"Created file: {filepath}")
                created_files.append(str(filepath))
                
                # Record the file creation in working memory
                if 'created_files' not in self.working_memory:
                    self.working_memory['created_files'] = []
                self.working_memory['created_files'].append({
                    'path': str(filepath),
                    'timestamp': time.time(),
                    'size': len(doc['content'])
                })
                
                # If it seems like an important file, add to important files list
                important_extensions = ['.py', '.json', '.md', '.sh', '.yaml', '.yml', '.conf', '.txt']
                if any(str(filepath).endswith(ext) for ext in important_extensions):
                    if 'important_files' not in self.working_memory:
                        self.working_memory['important_files'] = []
                    if str(filepath) not in self.working_memory.get('important_files', []):
                        self.working_memory['important_files'].append(str(filepath))
                
            except Exception as e:
                logger.error(f"Error creating file {doc['filename']}: {e}")
                
        return created_files

    def _setup_storage(self):
        """Ensure required directories exist under ./memory/"""
        dirs = [
            'conversations',
            'logs',
            'summaries',
            'config',
            'scripts',
            'data',
            'temp',
            'state',
            'sessions',
            'reflections',
            'working_memory',
            'tasks',
            'plans',
            'archive',
            'notes'
        ]
        for dir_name in dirs:
            (self.memory_path / dir_name).mkdir(parents=True, exist_ok=True)
            
    async def _save_working_memory_state(self):
        """Save current working memory state to disk"""
        try:
            # Only save if working memory has content
            if not self.working_memory:
                return
                
            # Create a file with the current timestamp
            timestamp = int(time.time())
            memory_file = self.memory_path / "working_memory" / f"state_{timestamp}.json"
            
            with open(memory_file, 'w') as f:
                json.dump(self.working_memory, f, indent=2, default=str)
                
            # Only keep the last 10 states to avoid disk fill
            memory_files = sorted(list((self.memory_path / "working_memory").glob("state_*.json")), 
                                key=lambda f: f.stat().st_mtime)
            if len(memory_files) > 10:
                for old_file in memory_files[:-10]:
                    old_file.unlink()
                    
        except Exception as e:
            logger.error(f"Error saving working memory state: {e}")
            
    def _enhance_system_prompt(self, system_prompt: str) -> str:
        """Add contextual information to system prompt"""
        try:
            # Detect system information
            system_info = self._detect_system_info()
            
            # Add agent identity and status
            identity_section = f"""
# Agent Identity and Status
- Agent ID: {self.agent_id}
- Started: {self.agent_state['started_at']}
- Status: {self.agent_state['status']}
- Current working directory: {self.working_memory.get('working_directory', os.getcwd())}
"""
            
            # Add system information section
            system_info_section = f"""
# System Information
- OS Type: {system_info.get('os_type', 'Unknown')}
- Distribution: {system_info.get('distribution', 'Unknown')}
- Package Manager: {system_info.get('package_manager', 'Unknown')}
- Test Mode: {'Enabled - commands will not actually execute' if self.test_mode else 'Disabled - commands will execute normally'}
"""
            
            # Add memory stats if available
            memory_stats = ""
            if hasattr(self.memory_manager, 'memory_stats'):
                memory_stats = "\n# Memory Status\n"
                for k, v in self.memory_manager.memory_stats.items():
                    if k != 'last_backup_time':  # Skip timestamp fields
                        memory_stats += f"- {k}: {v}\n"
            
            # Add important files if any have been stored
            files_section = ""
            if 'important_files' in self.working_memory and self.working_memory['important_files']:
                files_section = "\n# Important Files\n"
                for file_path in self.working_memory['important_files'][:5]:  # Limit to 5 files
                    files_section += f"- {file_path}\n"
            
            # Add task information if available
            tasks_section = ""
            if 'tasks' in self.working_memory and self.working_memory['tasks']:
                tasks_section = "\n# Active Tasks\n"
                for task in self.working_memory['tasks'][-3:]:  # Show last 3 tasks
                    tasks_section += f"- {task.get('title', 'Untitled task')} (Status: {task.get('status', 'pending')})\n"
                    
            # Combine all sections
            combined_prompt = f"{system_prompt}\n\n{identity_section}{system_info_section}{memory_stats}{files_section}{tasks_section}"
            return combined_prompt
            
        except Exception as e:
            logger.error(f"Error enhancing system prompt: {e}")
            return system_prompt  # Return original if there's an error
            
    def _detect_system_info(self) -> dict:
        """Detect information about the current system environment"""
        system_info = {
            'os_type': 'Unknown',
            'distribution': 'Unknown',
            'package_manager': 'Unknown',
            'shell': 'bash'
        }
        
        try:
            # Detect operating system
            if os.name == 'posix':
                system_info['os_type'] = 'Linux/Unix'
                
                # Try to detect distribution and package manager
                if os.path.exists('/etc/os-release'):
                    with open('/etc/os-release', 'r') as f:
                        os_release = f.read()
                        
                        # Check for common distributions
                        if 'ID=arch' in os_release or 'ID=manjaro' in os_release:
                            system_info['distribution'] = 'Arch Linux' if 'ID=arch' in os_release else 'Manjaro'
                            system_info['package_manager'] = 'pacman'
                        elif 'ID=ubuntu' in os_release or 'ID=debian' in os_release:
                            system_info['distribution'] = 'Ubuntu' if 'ID=ubuntu' in os_release else 'Debian'
                            system_info['package_manager'] = 'apt'
                        elif 'ID=fedora' in os_release or 'ID=rhel' in os_release or 'ID=centos' in os_release:
                            system_info['distribution'] = 'Fedora/RHEL/CentOS'
                            system_info['package_manager'] = 'dnf/yum'
                        elif 'ID=alpine' in os_release:
                            system_info['distribution'] = 'Alpine'
                            system_info['package_manager'] = 'apk'
                
                # Fallback detection based on common executables
                if system_info['package_manager'] == 'Unknown':
                    # Check common package managers
                    package_managers = {
                        'pacman': 'pacman',
                        'apt': 'apt',
                        'dnf': 'dnf',
                        'yum': 'yum',
                        'apk': 'apk'
                    }
                    
                    for pm_name, pm_cmd in package_managers.items():
                        # Check if the package manager exists in common paths
                        if any(os.path.exists(os.path.join(path, pm_cmd)) 
                               for path in ['/usr/bin', '/bin', '/usr/sbin', '/sbin']):
                            system_info['package_manager'] = pm_name
                            break
            
            elif os.name == 'nt':
                system_info['os_type'] = 'Windows'
                system_info['package_manager'] = 'choco/winget'
            elif os.name == 'darwin':
                system_info['os_type'] = 'macOS'
                system_info['package_manager'] = 'brew'
                
            # Store in working memory for future reference
            self.working_memory['system_info'] = system_info
            
            return system_info
            
        except Exception as e:
            logger.error(f"Error detecting system info: {e}")
            return system_info

    def _load_system_prompt(self, path: Path) -> str:
        """Load system prompt from file"""
        try:
            with open(path) as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"System prompt not found at {path}, using empty prompt")
            return ""

    def _load_last_session(self) -> Optional[str]:
        """Load summary of last session"""
        summary_path = self.memory_path / "summaries/last_session.txt"
        try:
            if summary_path.exists():
                with open(summary_path) as f:
                    return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading last session: {e}")
        return None

    def _save_session_summary(self, summary: str):
        """Save session summary for next run"""
        try:
            with open(self.memory_path / "summaries/last_session.txt", 'w') as f:
                f.write(summary)
        except Exception as e:
            logger.error(f"Error saving session summary: {e}")

    def _print_response(self, content: str):
        """Print agent's response with clear formatting"""
        print("\n=== LLM RESPONSE ===")
        print(content)
        print("=====================")

    def archive_session(self):
        """
        Archive the entire conversation in memory by writing it to a file under
        memory/sessions and also storing it as a conversation node in the memory graph.
        """
        timestamp = int(datetime.now().timestamp())
        session_filename = f"{timestamp}_session.json"
        session_path = self.memory_path / "sessions" / session_filename
        
        # Generate a session summary
        summary = self._generate_session_summary()

        data_to_save = {
            "conversation": self.local_conversation_history,
            "ended_at": datetime.now().isoformat(),
            "summary": summary
        }

        try:
            # Make sure the directory exists
            (self.memory_path / "sessions").mkdir(exist_ok=True)
            
            with open(session_path, "w") as f:
                json.dump(data_to_save, f, indent=2)
            logger.info(f"Session archived to {session_path}")
            
            # Also save a summary file for easy reference
            summary_file = self.memory_path / "summaries" / f"{timestamp}_summary.txt"
            (self.memory_path / "summaries").mkdir(exist_ok=True)
            with open(summary_file, "w") as f:
                f.write(summary)
                
            # Update last session summary
            with open(self.memory_path / "summaries/last_session.txt", "w") as f:
                f.write(summary)
        except Exception as e:
            logger.error(f"Error writing session archive: {e}")

        try:
            conversation_id = f"session_{timestamp}"
            self.memory_manager.save_conversation(
                conversation_id,
                messages=self.local_conversation_history,
                metadata={
                    "archived_at": datetime.now().isoformat(),
                    "summary": summary
                }
            )
            logger.info(f"Session also saved in memory graph as conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error saving session to memory graph: {e}")
            
    def _generate_session_summary(self) -> str:
        """Generate a summary of the current session"""
        try:
            # Extract all user messages
            user_msgs = [m['content'] for m in self.local_conversation_history if m.get('role') == 'user']
            
            # Extract all assistant messages
            assistant_msgs = [m['content'] for m in self.local_conversation_history if m.get('role') == 'assistant']
            
            # Extract all decisions, plans, and summaries
            decisions = []
            plans = []
            summaries = []
            for msg in assistant_msgs:
                decisions.extend(self.command_extractor.extract_decision(msg))
                plans.extend(self.command_extractor.extract_plan(msg))
                summaries.extend(self.command_extractor.extract_summary(msg))
            
            # Extract commands executed
            commands = []
            for msg in assistant_msgs:
                for tag in self.command_extractor.COMMAND_TAGS:
                    pattern = f"<{tag}>(.*?)</{tag}>"
                    matches = re.finditer(pattern, msg, re.DOTALL)
                    for match in matches:
                        cmd = match.group(1).strip().split('\n')[0]  # First line only
                        commands.append(f"{tag}: {cmd}")
            
            # Create a comprehensive summary
            summary_parts = []
            
            # Initial task
            if user_msgs:
                summary_parts.append("# Session Summary\n")
                summary_parts.append("## Initial Task")
                summary_parts.append(user_msgs[0][:300] + ("..." if len(user_msgs[0]) > 300 else ""))
            
            # Key decisions 
            if decisions:
                summary_parts.append("\n## Key Decisions")
                summary_parts.append("\n".join(decisions[:3]))
            
            # Plans developed
            if plans:
                summary_parts.append("\n## Plans")
                summary_parts.append("\n".join(plans[:2]))
            
            # Key commands executed
            if commands:
                summary_parts.append("\n## Key Commands")
                summary_parts.append("\n".join(commands[:10]))
                if len(commands) > 10:
                    summary_parts.append(f"...and {len(commands) - 10} more commands")
            
            # Final outcome
            if summaries:
                summary_parts.append("\n## Results and Outcomes")
                summary_parts.append("\n".join(summaries))
            elif assistant_msgs:
                # If no explicit summaries, use the last assistant message
                summary_parts.append("\n## Final Message")
                summary_parts.append(assistant_msgs[-1][:300] + ("..." if len(assistant_msgs[-1]) > 300 else ""))
            
            return "\n\n".join(summary_parts)
        except Exception as e:
            logger.error(f"Error generating session summary: {e}")
            return f"Session completed at {datetime.now().isoformat()}"

    def cleanup(self):
        """Cleanup resources and save state"""
        try:
            # Create a final backup of memory state
            self.memory_manager.create_backup()
            
            # Save command history
            history_path = self.memory_path / "state/command_history.json"
            (self.memory_path / "state").mkdir(exist_ok=True)
            
            with open(history_path, 'w') as f:
                json.dump(self.command_history, f, indent=2)
            
            self.system_control.cleanup()
            
            # Archive the final session conversation
            self.archive_session()
            
            logger.info("Agent cleanup completed successfully")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def heartbeat(self):
        """Auto-save state every 2 minutes and perform health checks"""
        try:
            heartbeat_interval = 120  # 2 minutes
            while not self.should_exit:
                # Update agent state
                self.agent_state['heartbeat'] = datetime.now().isoformat()
                self._save_state()
                
                # Create backup during heartbeat
                self.memory_manager.create_backup()
                
                # Perform health check
                await self._health_check()
                
                await asyncio.sleep(heartbeat_interval)
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            
    async def _health_check(self):
        """Perform system health check and monitor agent state"""
        try:
            # Check if working memory is getting too large
            working_memory_size = len(json.dumps(self.working_memory))
            if working_memory_size > 500000:  # 500KB
                logger.warning(f"Working memory size too large: {working_memory_size} bytes. Pruning...")
                await self._prune_working_memory()
                
            # Log some basic stats
            stats = {
                'uptime': (datetime.now() - datetime.fromisoformat(self.agent_state['started_at'])).total_seconds(),
                'working_memory_size': working_memory_size,
                'conversation_turns': len(self.local_conversation_history) // 2,  # Approximate turn count
                'commands_executed': self.agent_state.get('commands_executed', 0)
            }
            logger.info(f"Agent health check: {stats}")
            
            # Save health stats to memory periodically
            if time.time() % 3600 < 120:  # Approximately once per hour
                self.memory_manager.save_document(
                    f"health_check_{int(time.time())}",
                    f"Agent health check at {datetime.now().isoformat()}\n" + 
                    "\n".join([f"{k}: {v}" for k, v in stats.items()]),
                    tags=["health", "monitoring"],
                    metadata=stats
                )
        except Exception as e:
            logger.error(f"Health check error: {e}")
            
    async def _monitor_resources(self):
        """Monitor system resources periodically"""
        try:
            while not self.should_exit:
                # Monitor memory directory size
                await self.system_control.monitor_resources()
                
                # Sleep for 5 minutes
                await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Resource monitoring error: {e}")
            
    async def _prune_working_memory(self):
        """Prune working memory when it gets too large"""
        try:
            # Keep only essential keys and recent performance data
            essential_keys = {'working_directory', 'session_id', 'current_task', 'important_files'}
            preserve = {k: self.working_memory[k] for k in essential_keys if k in self.working_memory}
            
            # Keep only the last 10 performance records
            if 'performance' in self.working_memory and isinstance(self.working_memory['performance'], list):
                preserve['performance'] = self.working_memory['performance'][-10:]
                
            # Replace working memory with pruned version
            old_size = len(json.dumps(self.working_memory))
            self.working_memory = preserve
            new_size = len(json.dumps(self.working_memory))
            
            logger.info(f"Pruned working memory from {old_size} to {new_size} bytes")
            
            # Save a snapshot of the full working memory before pruning
            self.memory_manager.save_document(
                f"working_memory_snapshot_{int(time.time())}",
                json.dumps(self.working_memory, indent=2),
                tags=["memory", "snapshot", "pruned"],
                metadata={"reason": "size_limit_exceeded", "old_size": old_size, "new_size": new_size}
            )
        except Exception as e:
            logger.error(f"Error pruning working memory: {e}")

    def _save_state(self):
        """Save critical state information periodically"""
        try:
            # Get active tasks from task manager
            tasks = self.task_manager.active_tasks
            
            # Create a comprehensive state object
            state = {
                "tasks": tasks,
                "environment": dict(os.environ),
                "last_commands": self.command_history[-10:] if self.command_history else [],
                "session_summary": self.last_session_summary,
                "conversation_length": len(self.local_conversation_history),
                "last_heartbeat": datetime.now().isoformat(),
                "system_stats": {
                    "memory_nodes": len(self.memory_manager.graph.graph.nodes),
                    "command_history_length": len(self.memory_manager.command_history)
                }
            }
            
            # Save to document store
            self.memory_manager.save_document(
                "system_state", 
                json.dumps(state, indent=2),
                tags=["system", "state", "heartbeat"],
                metadata={"timestamp": time.time()}
            )
            
            logger.info(f"State saved - {len(state['tasks'])} tasks, {state['conversation_length']} messages")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            # Still try to save minimal state
            try:
                self.memory_manager.save_document(
                    "emergency_state", 
                    json.dumps({"error": str(e), "timestamp": time.time()}),
                    tags=["system", "error"]
                )
            except:
                pass

    async def compress_context(self, messages: List[Dict], token_limit: int = 16000) -> List[Dict]:
        """
        Compress conversation context when it gets too large.
        Implements smart summarization of earlier exchanges while keeping recent messages intact.
        
        Args:
            messages: List of conversation messages
            token_limit: Target token limit (approximate)
            
        Returns:
            Compressed message list that fits within the token limit
        """
        # Simple and conservative estimate - each char is roughly 0.25 tokens
        estimated_tokens = sum(len(str(msg.get('content', ''))) for msg in messages) // 4
        
        if estimated_tokens <= token_limit:
            return messages  # No compression needed
        
        try:
            # Record compression event
            compression_start = time.time()
            pre_compression_size = estimated_tokens
            
            # Keep system message, last 3 user exchanges, and summarize earlier parts
            system_messages = [msg for msg in messages if msg.get('role') == 'system']
            user_messages = [msg for msg in messages if msg.get('role') == 'user']
            assistant_messages = [msg for msg in messages if msg.get('role') == 'assistant']
            
            # Always keep system messages
            kept_messages = system_messages.copy()
            
            # Determine how many recent exchanges to keep
            # One exchange is one user message followed by one assistant message
            exchanges_to_keep = min(3, len(user_messages))
            
            # Keep recent exchanges (user + assistant pairs)
            for i in range(1, exchanges_to_keep + 1):
                if i <= len(user_messages):
                    kept_messages.append(user_messages[-i])
                    if i <= len(assistant_messages):
                        kept_messages.append(assistant_messages[-i])
            
            # Sort by original order
            kept_messages.sort(key=lambda m: messages.index(m))
            
            # Messages to summarize are ones not kept
            to_summarize = [m for m in messages if m not in kept_messages]
            
            if not to_summarize:
                return kept_messages  # No messages to summarize
            
            # Group messages to summarize by role
            user_to_summarize = [m['content'] for m in to_summarize if m.get('role') == 'user']
            assistant_to_summarize = [m['content'] for m in to_summarize if m.get('role') == 'assistant']
            
            # Create summary
            summary_parts = []
            
            # Add a clear header to indicate this is a summary
            summary_parts.append("## PREVIOUS CONVERSATION SUMMARY")
            summary_parts.append(f"(Summarizing {len(to_summarize)} earlier messages)")
            
            # Summarize user messages
            if user_to_summarize:
                summary_parts.append("\n### User Messages")
                # Extract key questions
                questions = []
                for msg in user_to_summarize:
                    # Look for question marks or implied questions
                    lines = msg.split('\n')
                    for line in lines:
                        if '?' in line or any(starter in line.lower() for starter in 
                                            ['how ', 'what ', 'when ', 'where ', 'why ', 'can you', 'please ']):
                            questions.append(line.strip())
                
                if questions:
                    summary_parts.append("Key questions:")
                    for i, q in enumerate(questions[:5]):
                        summary_parts.append(f"- {q[:100]}{'...' if len(q) > 100 else ''}")
                    if len(questions) > 5:
                        summary_parts.append(f"- ...and {len(questions) - 5} more questions")
                else:
                    # Just summarize general topics
                    summary_parts.append("General topics mentioned:")
                    topic_summary = "; ".join([m[:50] + ('...' if len(m) > 50 else '') for m in user_to_summarize[:3]])
                    summary_parts.append(f"- {topic_summary}")
            
            # Summarize assistant messages
            if assistant_to_summarize:
                summary_parts.append("\n### Assistant Actions")
                
                # Extract command patterns as they're important
                all_commands = []
                for msg in assistant_to_summarize:
                    for tag in CommandExtractor.COMMAND_TAGS:
                        pattern = f"<{tag}>(.*?)</{tag}>"
                        matches = re.finditer(pattern, msg, re.DOTALL)
                        for match in matches:
                            cmd = match.group(1).strip().split('\n')[0][:50]  # Just first line, limited length
                            all_commands.append(f"{tag}: {cmd}...")
                
                # Extract insights from reasoning blocks
                insights = []
                thinking_patterns = ["<thinking>(.*?)</thinking>", "<decision>(.*?)</decision>", "<plan>(.*?)</plan>"]
                for msg in assistant_to_summarize:
                    for pattern in thinking_patterns:
                        matches = re.finditer(pattern, msg, re.DOTALL)
                        for match in matches:
                            content = match.group(1).strip()
                            # Extract key sentences
                            sentences = re.split(r'[.!?]\s+', content)
                            for sentence in sentences:
                                if len(sentence) > 10 and len(sentence) < 100:
                                    if any(kw in sentence.lower() for kw in ['should', 'important', 'need', 'key', 'critical']):
                                        insights.append(sentence)
                
                # Add commands executed
                if all_commands:
                    summary_parts.append("Previous commands:")
                    for cmd in all_commands[:5]:
                        summary_parts.append(f"- {cmd}")
                    if len(all_commands) > 5:
                        summary_parts.append(f"- ...and {len(all_commands) - 5} more commands")
                else:
                    summary_parts.append("No commands were executed in the summarized portion.")
                
                # Add key insights
                if insights:
                    summary_parts.append("\nKey insights:")
                    for insight in insights[:3]:
                        summary_parts.append(f"- {insight}")
            
            # Add important context from working memory
            if self.working_memory:
                summary_parts.append("\n### Important Context")
                
                # Add important files if tracked
                if 'important_files' in self.working_memory and self.working_memory['important_files']:
                    summary_parts.append("Important files:")
                    for file in self.working_memory['important_files'][:5]:
                        summary_parts.append(f"- {file}")
                
                # Add current task if available
                if 'current_task' in self.working_memory:
                    summary_parts.append(f"\nCurrent task: {self.working_memory['current_task']}")
            
            # Add relevant context from memory
            if len(kept_messages) <= 7:  # Only add if we don't have many messages already
                # Get recent memories that might be relevant based on the most recent user message
                if user_messages:
                    recent_query = user_messages[-1].get('content', '')
                    if len(recent_query) > 10:
                        results = self.memory_manager.search_memory(
                            recent_query, 
                            limit=3,
                            tags=["important", "documentation", "decision"],
                            recency_boost=True
                        )
                        if results:
                            summary_parts.append("\n### Relevant Memory Items")
                            for r in results:
                                # Only include short snippets
                                content = r.get('content', '')
                                title = r.get('title', 'Untitled')
                                if len(content) > 500:
                                    content = content[:500] + "..."
                                summary_parts.append(f"- {title}: {content}")
            
            # Combine all summary parts
            summary = "\n".join(summary_parts)
            
            # Create a document version of this summary for future reference
            summary_doc_id = f"context_summary_{int(time.time())}"
            self.memory_manager.save_document(
                summary_doc_id,
                summary,
                tags=["summary", "context", "compression"],
                metadata={
                    "original_messages": len(messages),
                    "kept_messages": len(kept_messages),
                    "summarized_messages": len(to_summarize),
                    "original_tokens": pre_compression_size,
                }
            )
            
            # Add the summary as a system message at the start
            kept_messages.insert(0 if not system_messages else 1, 
                               {"role": "system", "content": summary})
            
            # Log compression stats
            post_size = sum(len(str(msg.get('content', ''))) for msg in kept_messages) // 4
            compression_time = time.time() - compression_start
            logger.info(f"Context compressed from {pre_compression_size} to {post_size} tokens in {compression_time:.2f}s")
            
            return kept_messages
            
        except Exception as e:
            logger.error(f"Error during context compression: {e}")
            # Simple fallback - keep system message and last few exchanges
            return messages[-10:] if len(messages) > 10 else messages
    
    # Missing helper methods
    async def _handle_no_commands(self, response: str, session_id: str, turn_count: int) -> None:
        """Handle cases where no commands were extracted from the response"""
        try:
            # Check for explicit completion signals
            completion_signals = [
                "session_end", "task complete", "all done", 
                "completed successfully", "finished the task", "all tasks completed"
            ]
            
            if any(signal in response.lower() for signal in completion_signals):
                # Record completion in memory
                self.memory_manager.save_document(
                    f"task_completion_{session_id}_{turn_count}",
                    f"Task completed at turn {turn_count}.\nFinal message: {response[:500]}",
                    tags=["task", "completion"],
                    metadata={
                        "session_id": session_id,
                        "turn": turn_count,
                        "status": "completed"
                    }
                )
                
                print("Agent declared task completion. Ending session.")
                self.should_exit = True
                self.agent_state['status'] = 'completed'
                self.agent_state['tasks_completed'] += 1
                return
                
            # If no completion signals, ask for commands
            next_user_msg = {
                "role": "user",
                "content": "(No commands found - Please provide commands to execute or declare session end.)"
            }
            self.local_conversation_history.append(next_user_msg)
            
            # Log the event
            logger.info(f"No commands found in turn {turn_count}")
            
        except Exception as e:
            logger.error(f"Error handling no commands case: {e}")

    async def _execute_commands(self, commands: List[Tuple[str, str]], 
                              session_id: str, turn_count: int) -> List[str]:
        """Execute commands and process their outputs with timeout protection"""
        all_outputs = []
        command_execution_errors = 0
        max_command_errors = 3  # Tolerate up to 3 command errors before giving up
        
        # Update agent state
        self.agent_state['last_active'] = datetime.now().isoformat()
        
        for cmd_idx, (cmd_type, cmd_content) in enumerate(commands):
            # Check for exit commands
            if self.command_extractor.is_exit_command(cmd_type, cmd_content):
                print("Agent used an exit command. Ending session.")
                self.should_exit = True
                break
            
            # Log command execution
            cmd_id = f"{session_id}_{turn_count}_{cmd_idx}"
            logger.info(f"Executing command {cmd_id}: {cmd_type} - {cmd_content[:50]}...")
            
            # Determine appropriate timeout for this command
            # Longer timeout for commands likely to take more time
            standard_timeout = 120  # 2 minutes
            if any(slow_cmd in cmd_content.lower() for slow_cmd in 
                  ['install', 'update', 'upgrade', 'train', 'download', 'build', 'compile']):
                command_timeout = 300  # 5 minutes for commands likely to take longer
            else:
                command_timeout = standard_timeout
                
            # Save command to memory before execution
            self.memory_manager.save_document(
                f"command_{cmd_id}",
                f"Type: {cmd_type}\nCommand:\n{cmd_content}",
                tags=["command", cmd_type, "execution"],
                metadata={
                    "session_id": session_id,
                    "turn": turn_count,
                    "command_index": cmd_idx,
                    "command_type": cmd_type,
                    "status": "started",
                    "timeout": command_timeout
                }
            )
            
            # Actually execute the commands
            if self.test_mode:
                # In test mode, we don't really execute
                output = f"[TEST MODE] Would have executed {cmd_type} command: {cmd_content}"
                print(output)
                all_outputs.append(output)
                # Log to memory manager
                self.memory_manager.add_command_to_history(cmd_content, cmd_type, success=True)
                
                # Update agent state
                self.agent_state['commands_executed'] += 1
                
            else:
                try:
                    # Record start time
                    start_time = time.time()
                    
                    # Handle file operation commands differently
                    if cmd_type in self.command_extractor.FILE_OP_TAGS:
                        result = await self._execute_file_operation(cmd_type, cmd_content, cmd_id)
                        all_outputs.append(f"FILE OPERATION RESULT:\n{result}")
                        
                        # Record in memory
                        self.memory_manager.save_document(
                            f"file_op_result_{cmd_id}",
                            result,
                            tags=["file_operation", cmd_type, "result"],
                            metadata={
                                "session_id": session_id,
                                "turn": turn_count,
                                "command_index": cmd_idx,
                                "operation_type": cmd_type,
                                "status": "completed"
                            }
                        )
                    else:
                        # Execute standard command with timeout
                        stdout, stderr, code = await self.system_control.execute_command(
                            cmd_type, 
                            cmd_content, 
                            interactive=(cmd_type == 'bash' and ('apt' in cmd_content or 'npm' in cmd_content)),
                            timeout=command_timeout
                        )
                        
                        # Save command usage to command history
                        self.memory_manager.add_command_to_history(cmd_content, cmd_type, code == 0)
                        
                        # Calculate execution time
                        execution_time = time.time() - start_time
                        
                        # Create a structured output
                        combined_output = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}\nEXIT CODE: {code}\nEXECUTION TIME: {execution_time:.2f}s"
                        all_outputs.append(combined_output)
                        
                        # Update agent state
                        self.agent_state['commands_executed'] += 1
                        
                        # Update command record in memory
                        self.memory_manager.save_document(
                            f"command_result_{cmd_id}",
                            combined_output,
                            tags=["command", cmd_type, "result", "success" if code == 0 else "failure"],
                            metadata={
                                "session_id": session_id,
                                "turn": turn_count,
                                "command_index": cmd_idx,
                                "exit_code": code,
                                "execution_time": execution_time,
                                "status": "completed",
                                "timeout_used": command_timeout
                            }
                        )
                        
                        # Check if command failed
                        if code != 0:
                            logger.warning(f"Command failed with exit code {code}")
                            command_execution_errors += 1
                            
                            # Check for timeout in stderr
                            if "timed out" in stderr.lower():
                                logger.warning(f"Command timed out after {command_timeout}s: {cmd_content[:80]}")
                                all_outputs.append(f"\nNote: The previous command timed out after {command_timeout} seconds. Consider using a simpler approach or breaking it into smaller steps.")
                            
                            if command_execution_errors >= max_command_errors:
                                error_message = "\nToo many command errors. Please review and adjust your approach."
                                all_outputs.append(error_message)
                                break
                            
                except asyncio.TimeoutError:
                    # Handle timeout at this level too
                    error_msg = f"Command execution timed out after {command_timeout} seconds"
                    logger.error(error_msg)
                    all_outputs.append(f"ERROR: {error_msg}")
                    command_execution_errors += 1
                            
                except Exception as cmd_error:
                    error_msg = f"ERROR executing {cmd_type} command: {str(cmd_error)}"
                    logger.error(error_msg)
                    all_outputs.append(error_msg)
                    command_execution_errors += 1
                    
                    # Record error in memory
                    self.memory_manager.save_document(
                        f"command_error_{cmd_id}",
                        f"Error executing command:\n{error_msg}\n\nCommand was:\n{cmd_content}",
                        tags=["command", cmd_type, "error"],
                        metadata={
                            "session_id": session_id,
                            "turn": turn_count,
                            "command_index": cmd_idx,
                            "error": str(cmd_error),
                            "status": "error"
                        }
                    )
                    
                    if command_execution_errors >= max_command_errors:
                        all_outputs.append("\nToo many command errors. Please review and adjust your approach.")
                        break
            
            # Check if we should exit after this command
            if self.should_exit:
                break
                
        return all_outputs
        
    async def _execute_file_operation(self, op_type: str, content: str, cmd_id: str) -> str:
        """
        Execute file operation commands.
        
        Args:
            op_type: Type of file operation ('view', 'edit', 'replace', 'glob', 'grep', 'ls')
            content: The command parameters
            cmd_id: Unique command ID for logging
            
        Returns:
            Operation result as string
        """
        try:
            # Parse parameters from content
            params = self._parse_file_operation_params(content)
            
            # Execute appropriate file operation
            if op_type == 'view':
                file_path = params.get('file_path', '')
                offset = int(params.get('offset', '0'))
                limit = int(params.get('limit', '2000'))
                
                if not file_path:
                    return "Error: Missing file_path parameter"
                    
                return await self.system_control.view_file(file_path, offset, limit)
                
            elif op_type == 'edit':
                file_path = params.get('file_path', '')
                old_string = params.get('old_string', '')
                new_string = params.get('new_string', '')
                
                if not file_path:
                    return "Error: Missing file_path parameter"
                    
                return await self.system_control.edit_file(file_path, old_string, new_string)
                
            elif op_type == 'replace':
                file_path = params.get('file_path', '')
                content = params.get('content', '')
                
                if not file_path:
                    return "Error: Missing file_path parameter"
                    
                return await self.system_control.replace_file(file_path, content)
                
            elif op_type == 'glob':
                pattern = params.get('pattern', '')
                path = params.get('path', None)
                
                if not pattern:
                    return "Error: Missing pattern parameter"
                    
                results = await self.system_control.glob_search(pattern, path)
                return "\n".join(results) if isinstance(results, list) else str(results)
                
            elif op_type == 'grep':
                pattern = params.get('pattern', '')
                include = params.get('include', None)
                path = params.get('path', None)
                
                if not pattern:
                    return "Error: Missing pattern parameter"
                    
                results = await self.system_control.grep_search(pattern, include, path)
                
                # Format results for display
                if isinstance(results, list):
                    formatted_results = []
                    for item in results:
                        if isinstance(item, dict):
                            if 'error' in item:
                                formatted_results.append(f"ERROR: {item['error']}")
                            elif 'message' in item:
                                formatted_results.append(item['message'])
                            elif 'file' in item and 'line_number' in item and 'line' in item:
                                formatted_results.append(f"{item['file']}:{item['line_number']}: {item['line']}")
                            else:
                                formatted_results.append(str(item))
                        else:
                            formatted_results.append(str(item))
                    return "\n".join(formatted_results)
                
                return str(results)
                
            elif op_type == 'ls':
                path = params.get('path', '')
                
                if not path:
                    return "Error: Missing path parameter"
                    
                result = await self.system_control.list_directory(path)
                
                # Format result for display
                if isinstance(result, dict):
                    if 'error' in result:
                        return f"ERROR: {result['error']}"
                        
                    formatted_result = [f"Directory: {result.get('path', '')}"]
                    
                    if 'directories' in result and result['directories']:
                        formatted_result.append("\nDirectories:")
                        for directory in result['directories']:
                            formatted_result.append(f"  {directory}/")
                            
                    if 'files' in result and result['files']:
                        formatted_result.append("\nFiles:")
                        for file_info in result['files']:
                            name = file_info.get('name', '')
                            size = file_info.get('size', 0)
                            
                            # Format size
                            size_str = f"{size} bytes"
                            if size >= 1024 * 1024:
                                size_str = f"{size / (1024 * 1024):.2f} MB"
                            elif size >= 1024:
                                size_str = f"{size / 1024:.2f} KB"
                                
                            formatted_result.append(f"  {name} ({size_str})")
                            
                    return "\n".join(formatted_result)
                
                return str(result)
                
            else:
                return f"Error: Unsupported file operation type: {op_type}"
                
        except Exception as e:
            logger.error(f"Error executing file operation {op_type}: {str(e)}")
            return f"Error executing {op_type} operation: {str(e)}"
            
    def _parse_file_operation_params(self, content: str) -> Dict[str, str]:
        """
        Parse parameters from file operation command content.
        
        Args:
            content: Command content string
            
        Returns:
            Dictionary of parameter name to value
        """
        params = {}
        
        # Try JSON format first
        try:
            if content.strip().startswith('{') and content.strip().endswith('}'):
                import json
                params = json.loads(content)
                return params
        except:
            pass
            
        # Try key-value format (param: value)
        lines = content.split('\n')
        current_param = None
        current_value = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for param: value pattern
            match = re.match(r'^([a-zA-Z_]+)\s*:\s*(.*)$', line)
            if match:
                # Save previous parameter if any
                if current_param:
                    params[current_param] = '\n'.join(current_value).strip()
                    
                # Start new parameter
                current_param = match.group(1)
                current_value = [match.group(2)]
            elif current_param:
                # Continue multi-line value
                current_value.append(line)
        
        # Save last parameter
        if current_param:
            params[current_param] = '\n'.join(current_value).strip()
            
        return params
        
    async def _generate_final_reflection(self, session_id: str, turn_count: int) -> None:
        """Generate a final reflection about the session's progress and outcomes"""
        try:
            # Create a comprehensive reflection
            reflection_parts = []
            
            # Add basic session info
            reflection_parts.append(f"# Session Reflection - {session_id}")
            reflection_parts.append(f"Generated at: {datetime.now().isoformat()}")
            reflection_parts.append(f"Total turns: {turn_count}")
            reflection_parts.append(f"Commands executed: {self.agent_state.get('commands_executed', 0)}")
            
            # Add reflection on what was done
            reflection_parts.append("\n## Actions Taken")
            if self.working_memory.get('created_files'):
                reflection_parts.append("Files created:")
                for file_info in self.working_memory['created_files'][-10:]:  # Show last 10 created files
                    reflection_parts.append(f"- {file_info['path']}")
            
            # Add executive summary if available
            if self.executive_summary:
                reflection_parts.append("\n## Executive Summary")
                reflection_parts.append(self.executive_summary)
            
            # Add analysis of progress
            reflection_parts.append("\n## Progress Assessment")
            completed = "completed" in self.agent_state['status'].lower()
            if completed:
                reflection_parts.append("✅ Task was successfully completed.")
            else:
                reflection_parts.append("⚠️ Task was not explicitly marked as completed.")
                
            # Add performance data
            if 'performance' in self.working_memory and self.working_memory['performance']:
                reflection_parts.append("\n## Performance Metrics")
                perf_data = self.working_memory['performance']
                avg_turn_time = sum(p['duration'] for p in perf_data) / len(perf_data)
                reflection_parts.append(f"Average turn processing time: {avg_turn_time:.2f}s")
                
            # Save the reflection to a file
            reflection_content = "\n\n".join(reflection_parts)
            reflection_path = self.memory_path / "reflections" / f"session_{session_id}.md"
            with open(reflection_path, 'w') as f:
                f.write(reflection_content)
                
            # Also save to memory
            self.memory_manager.save_document(
                f"reflection_{session_id}",
                reflection_content,
                tags=["reflection", "session", "permanent"],
                permanent=True,
                metadata={
                    "session_id": session_id,
                    "turn_count": turn_count,
                    "completed": completed
                }
            )
            
            logger.info(f"Generated final reflection for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error generating final reflection: {e}")

    async def _request_user_input(self, question: str) -> str:
        """
        Request and get input from the user during agent execution.
        
        Args:
            question: The question or prompt to display to the user
            
        Returns:
            User's input response
        """
        try:
            # Record the pause in working memory
            if 'user_interactions' not in self.working_memory:
                self.working_memory['user_interactions'] = []
                
            self.working_memory['user_interactions'].append({
                'timestamp': time.time(),
                'question': question
            })
            
            # Present the question to the user with clear formatting
            print("\n" + "="*50)
            print("AGENT PAUSED AND REQUESTING YOUR INPUT:")
            print("-"*50)
            print(question)
            print("-"*50)
            
            # Get multi-line input from the user
            print("Enter your response (press Enter on a blank line to finish):")
            lines = []
            while True:
                try:
                    line = input()
                    # If the line is empty (no text), we finish collecting
                    if not line.strip():
                        break
                    lines.append(line)
                except EOFError:
                    break
                    
            user_input = "\n".join(lines)
            
            if not user_input.strip():
                # Provide a default response if the user didn't enter anything
                user_input = "(User acknowledged but provided no specific input)"
                
            # Record the user's response in working memory
            self.working_memory['user_interactions'][-1]['response'] = user_input
            
            print("="*50 + "\n")
            print("Thank you for your input. Continuing execution...\n")
            
            # Log the interaction
            logger.info(f"Received user input in response to agent question")
            
            return user_input
            
        except Exception as e:
            logger.error(f"Error getting user input: {e}")
            # Return a fallback response in case of error
            return "There was an error processing your input. Please continue."

    async def _process_reasoning_blocks(self, response: str, session_id: str, turn_count: int) -> None:
        """Process and store reasoning blocks from the agent's response"""
        try:
            # Extract all reasoning blocks
            reasoning_data = {}
            for tag_name, extractor_method in [
                ("thinking", self.command_extractor.extract_thinking),
                ("decision", self.command_extractor.extract_decision),
                ("plan", self.command_extractor.extract_plan),
                ("summary", self.command_extractor.extract_summary),
                ("task", self.command_extractor.extract_tasks),
                ("subtask", self.command_extractor.extract_subtasks)
            ]:
                blocks = extractor_method(response)
                if blocks:
                    reasoning_data[tag_name] = blocks
                    
                    # Save to memory with session context
                    self.memory_manager.save_document(
                        f"{tag_name}_{session_id}_{turn_count}",
                        "\n\n".join(blocks),
                        tags=[tag_name, "reasoning", "chain_of_thought"],
                        metadata={
                            "session_id": session_id,
                            "turn": turn_count,
                            "block_type": tag_name
                        }
                    )
                    
                    # Add to agent state for reflection
                    if tag_name == "thinking":
                        self.reflections.append({
                            "type": "thinking",
                            "content": "\n\n".join(blocks),
                            "turn": turn_count,
                            "timestamp": time.time()
                        })
                    elif tag_name == "plan":
                        self.planned_steps.append({
                            "content": "\n\n".join(blocks),
                            "turn": turn_count,
                            "timestamp": time.time(),
                            "completed": False
                        })
                    elif tag_name == "summary" and blocks:
                        self.executive_summary = blocks[0]  # Keep the most recent summary
                    elif tag_name == "task":
                        # Process each task and add to task manager
                        for task_content in blocks:
                            # Extract task title if present (first line)
                            task_lines = task_content.split('\n')
                            task_title = task_lines[0].strip()
                            task_details = '\n'.join(task_lines[1:]).strip() if len(task_lines) > 1 else ""
                            
                            # Create a unique task ID
                            task_id = f"task_{int(time.time())}_{hash(task_title) % 10000}"
                            
                            # Add to task manager
                            self.task_manager.add_task(
                                task_id=task_id,
                                title=task_title,
                                description=task_details,
                                session_id=session_id,
                                metadata={
                                    "created_at": time.time(),
                                    "status": "pending",
                                    "priority": "medium"  # Default priority
                                }
                            )
                            
                            # Log task creation
                            logger.info(f"Created new task: {task_title}")
                            
                            # Add to working memory for short-term tracking
                            if 'tasks' not in self.working_memory:
                                self.working_memory['tasks'] = []
                            
                            self.working_memory['tasks'].append({
                                "id": task_id,
                                "title": task_title,
                                "created_at": time.time(),
                                "status": "pending"
                            })
                    
                    elif tag_name == "subtask":
                        # Process subtasks by linking them to the most recently created task
                        if reasoning_data.get("task") and 'tasks' in self.working_memory and self.working_memory['tasks']:
                            parent_task_id = self.working_memory['tasks'][-1]["id"]
                            
                            for subtask_content in blocks:
                                # Extract subtask title and details
                                subtask_lines = subtask_content.split('\n')
                                subtask_title = subtask_lines[0].strip()
                                subtask_details = '\n'.join(subtask_lines[1:]).strip() if len(subtask_lines) > 1 else ""
                                
                                # Create a unique subtask ID
                                subtask_id = f"subtask_{int(time.time())}_{hash(subtask_title) % 10000}"
                                
                                # Add to task manager as a subtask
                                self.task_manager.add_subtask(
                                    parent_id=parent_task_id,
                                    subtask_id=subtask_id,
                                    title=subtask_title,
                                    description=subtask_details,
                                    metadata={
                                        "created_at": time.time(),
                                        "status": "pending"
                                    }
                                )
                                
                                logger.info(f"Created subtask '{subtask_title}' for task {parent_task_id}")
                        
            # Also save to working memory (limited history)
            if reasoning_data:
                if 'reasoning_history' not in self.working_memory:
                    self.working_memory['reasoning_history'] = []
                
                # Add new reasoning data
                self.working_memory['reasoning_history'].append({
                    "turn": turn_count,
                    "timestamp": time.time(),
                    "data": reasoning_data
                })
                
                # Keep only the last 5 turns of reasoning history
                if len(self.working_memory['reasoning_history']) > 5:
                    self.working_memory['reasoning_history'] = self.working_memory['reasoning_history'][-5:]
                    
        except Exception as e:
            logger.error(f"Error processing reasoning blocks: {e}")
            
        
