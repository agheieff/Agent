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
            
        # Conversation state tracking for human pause feature
        self.last_assistant_response = None
        self.paused_for_human_context = False

        # Get memory location from memory_manager or create a new one
        if memory_manager:
            self.memory_manager = memory_manager
        else:
            self.memory_manager = MemoryManager()
            
        self.memory_path = self.memory_manager.base_path
        self._setup_storage()
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
        
        Special commands:
        - /compact: Compresses conversation history to save context space
        - /help: Shows help information
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

            # Check for slash commands in initial prompt
            if initial_prompt.strip().startswith('/') and len(initial_prompt.strip().split()) == 1:
                cmd = initial_prompt.strip().lower()
                if cmd == '/compact':
                    # Special startup case, just give instructions
                    print("\nThe /compact command is used during an ongoing conversation.")
                    print("Starting a fresh conversation with an empty context...")
                    # Use a modified prompt that explains this
                    user_msg = {"role": "user", "content": "Please start a new conversation. I tried to use /compact but I need to have a conversation first before compacting it."}
                elif cmd == '/help':
                    # Special startup case, just give instructions and proceed
                    print("\nAvailable slash commands:")
                    print("  /help     - Show help information")
                    print("  /compact  - Compact conversation history to save context space")
                    print("\nStarting a new conversation...")
                    # Use a modified prompt that explains this
                    user_msg = {"role": "user", "content": "Please start a new conversation. I just checked the available commands with /help."}
                else:
                    # Unknown command, use as-is
                    user_msg = {"role": "user", "content": initial_prompt}
            else:
                # Normal prompt
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
                        
                        # Implement retry logic for potential API failures
                        max_retries = 3
                        retry_count = 0
                        retry_delay = 2  # Initial delay in seconds
                        
                        while retry_count < max_retries:
                            try:
                                response = await asyncio.wait_for(
                                    self.llm.get_response(
                                        prompt=None,
                                        system=None,
                                        conversation_history=compressed_history,
                                        tool_usage=False
                                    ),
                                    timeout=llm_timeout
                                )
                                if response:  # If we got a valid response, break the retry loop
                                    break
                                    
                                # If we got None but no exception, it's an API error, so retry
                                retry_count += 1
                                if retry_count >= max_retries:
                                    logger.error(f"LLM API call failed after {max_retries} attempts")
                                    # Create fallback response
                                    response = "I apologize, but I encountered issues connecting to the API. " + \
                                              "Let me try a simpler approach. Please give me a moment to reconsider."
                                    break
                                    
                                logger.warning(f"Retrying LLM API call (attempt {retry_count}/{max_retries})")
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                                
                            except (asyncio.TimeoutError, Exception) as api_error:
                                retry_count += 1
                                err_type = "timeout" if isinstance(api_error, asyncio.TimeoutError) else "error"
                                logger.error(f"LLM API {err_type} (attempt {retry_count}/{max_retries}): {str(api_error)}")
                                
                                if retry_count >= max_retries:
                                    # Create a special error response after all retries failed
                                    if isinstance(api_error, asyncio.TimeoutError):
                                        response = "I apologize, but my response was taking too long to generate. " + \
                                                  "Let me try a simpler approach. Please give me a moment to reconsider."
                                    else:
                                        response = f"I encountered an issue: {str(api_error)}. " + \
                                                  "Let me try a different approach. Please give me a moment to reconsider."
                                    break
                                    
                                # Wait before retry with exponential backoff
                                await asyncio.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                                
                    except asyncio.TimeoutError:
                        logger.error(f"LLM response timed out after {llm_timeout} seconds")
                        # Create a special error response
                        response = "I apologize, but my response was taking too long to generate. " + \
                                  "Let me try a simpler approach. Please give me a moment to reconsider."
                    except Exception as e:
                        logger.error(f"Unexpected error in LLM API call: {str(e)}")
                        response = f"I apologize, but I encountered an unexpected error: {str(e)}. " + \
                                  "Let me try a different approach. Please give me a moment to reconsider."
                    
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
                    
                    # Store the last assistant response for potential human context pausing
                    self.last_assistant_response = response
                    
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
                        
                    # Check for slash commands - this would be in next_user_msg
                    if len(self.local_conversation_history) > 0 and self.local_conversation_history[-1].get('role') == 'user':
                        user_content = self.local_conversation_history[-1].get('content', '')
                        if user_content.strip().startswith('/'):
                            cmd = user_content.strip().lower()
                            if cmd == '/compact':
                                # Force compression of context
                                print("\nCompacting conversation context...")
                                
                                # Save info about active state before compression
                                try:
                                    if hasattr(self.memory_manager, 'add_agent_note'):
                                        task_info = self.working_memory.get('current_task', 'Unknown task')
                                        state_note = f"Context compaction triggered at turn {self.memory_manager.conversation_turn_count}. Active task: {task_info}"
                                        self.memory_manager.add_agent_note(
                                            state_note,
                                            note_type="context_state",
                                            importance="high",
                                            tags=["compression", "context_window", "state"]
                                        )
                                except Exception as note_error:
                                    logger.error(f"Error saving state before compression: {note_error}")
                                
                                # Perform compression
                                compressed_history = await self.compress_context(self.local_conversation_history, force=True)
                                
                                # Replace the history with the compressed version
                                self.local_conversation_history = compressed_history
                                
                                # Record important working memory items in notes for persistence
                                try:
                                    for key in ['important_files', 'current_task']:
                                        if key in self.working_memory:
                                            if key == 'important_files' and isinstance(self.working_memory[key], list):
                                                files_note = f"Important files: {', '.join(self.working_memory[key][:10])}"
                                                if len(self.working_memory[key]) > 10:
                                                    files_note += f" and {len(self.working_memory[key]) - 10} more"
                                                
                                                self.memory_manager.add_agent_note(
                                                    files_note,
                                                    note_type="important_files",
                                                    importance="normal",
                                                    tags=["files", "state"]
                                                )
                                            elif key == 'current_task':
                                                self.memory_manager.add_agent_note(
                                                    f"Current task: {self.working_memory[key]}",
                                                    note_type="task_state",
                                                    importance="high", 
                                                    tags=["task", "state"]
                                                )
                                except Exception as mem_error:
                                    logger.error(f"Error preserving working memory items: {mem_error}")
                                
                                # Add a note about the compression with context about what to continue
                                continue_task = self.working_memory.get('current_task', 'the previous task')
                                user_msg = {
                                    "role": "user",
                                    "content": f"I've requested the conversation context to be compacted to save memory. Please continue with {continue_task}."
                                }
                                self.local_conversation_history.append(user_msg)
                                continue
                            elif cmd == '/pause':
                                # Handle pause command to add context
                                print("\n" + "="*60)
                                print("CONVERSATION PAUSED FOR ADDITIONAL CONTEXT")
                                print("-"*60)
                                print("Enter additional context to add to the conversation.")
                                print("This will be added to the agent's last response before continuing.")
                                print("Press Enter on a blank line when finished.")
                                print("-"*60)
                                
                                # Collect multi-line input
                                lines = []
                                while True:
                                    try:
                                        line = input()
                                        if not line.strip():
                                            break
                                        lines.append(line)
                                    except EOFError:
                                        break
                                        
                                additional_context = "\n".join(lines)
                                
                                if additional_context.strip():
                                    # Add the context to the conversation
                                    await self.add_human_context(additional_context)
                                    print("="*60)
                                    print("Context added. Conversation will continue.")
                                    print("="*60 + "\n")
                                    
                                    # Add a message indicating the context was added
                                    user_msg = {
                                        "role": "user",
                                        "content": "I've added additional context above. Please continue with that in mind."
                                    }
                                    self.local_conversation_history.append(user_msg)
                                else:
                                    print("No additional context provided. Continuing without changes.")
                                    # Add a simple continuation message
                                    user_msg = {
                                        "role": "user",
                                        "content": "Please continue with the previous task."
                                    }
                                    self.local_conversation_history.append(user_msg)
                                continue
                            elif cmd == '/help':
                                # Show help and continue
                                help_text = "\nAvailable Commands:\n"
                                help_text += "  /help     - Show this help message\n"
                                help_text += "  /compact  - Compact conversation history to save context space\n"
                                help_text += "  /pause    - Pause to add additional context to the conversation\n"
                                
                                print(help_text)
                                
                                # Add help text as user message
                                user_msg = {
                                    "role": "user", 
                                    "content": f"I requested help information. Please continue with the previous task."
                                }
                                self.local_conversation_history.append(user_msg)
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
                        
                        # Check if any output contains a slash command
                        slash_cmd = None
                        for output in all_outputs:
                            lines = output.strip().split('\n')
                            for line in lines:
                                if line.strip().startswith('/') and len(line.strip().split()) == 1:
                                    slash_cmd = line.strip().lower()
                                    break
                            if slash_cmd:
                                break
                        
                        # Handle slash commands in outputs
                        if slash_cmd == '/compact':
                            print("\nDetected /compact command in output. Compacting conversation context...")
                            compressed_history = await self.compress_context(self.local_conversation_history, force=True)
                            # Replace the history with the compressed version
                            self.local_conversation_history = compressed_history
                            # Add a modified message without the slash command
                            filtered_message = combined_message.replace('/compact', '(Context compacted)')
                            next_user_msg = {
                                "role": "user",
                                "content": filtered_message
                            }
                        elif slash_cmd == '/pause':
                            # Handle pause in output
                            print("\n" + "="*60)
                            print("CONVERSATION PAUSED FOR ADDITIONAL CONTEXT")
                            print("-"*60)
                            print("Enter additional context to add to the conversation.")
                            print("This will be added to the agent's last response before continuing.")
                            print("Press Enter on a blank line when finished.")
                            print("-"*60)
                            
                            # Collect multi-line input
                            lines = []
                            while True:
                                try:
                                    line = input()
                                    if not line.strip():
                                        break
                                    lines.append(line)
                                except EOFError:
                                    break
                                    
                            additional_context = "\n".join(lines)
                            
                            if additional_context.strip():
                                # Add the context to the conversation
                                await self.add_human_context(additional_context)
                                print("="*60)
                                print("Context added. Conversation will continue.")
                                print("="*60 + "\n")
                                
                                # Add a message indicating the context was added
                                filtered_message = combined_message.replace('/pause', '(Context added)')
                                next_user_msg = {
                                    "role": "user",
                                    "content": f"{filtered_message}\n\nI've added additional context to your last response. Please continue with that in mind."
                                }
                            else:
                                print("No additional context provided. Continuing without changes.")
                                # Add a simple continuation message with filtered command
                                filtered_message = combined_message.replace('/pause', '(Pause requested but no context added)')
                                next_user_msg = {
                                    "role": "user",
                                    "content": filtered_message
                                }
                        elif slash_cmd == '/help':
                            # Show help
                            help_text = "\nAvailable Commands:\n"
                            help_text += "  /help     - Show this help message\n"
                            help_text += "  /compact  - Compact conversation history to save context space\n"
                            help_text += "  /pause    - Pause to add additional context to the conversation\n"
                            print(help_text)
                            # Replace the command with a note
                            filtered_message = combined_message.replace('/help', '(Help displayed)')
                            next_user_msg = {
                                "role": "user",
                                "content": filtered_message
                            }
                        else:
                            # Normal message
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
            
            # Add conversation metrics
            conversation_metrics = ""
            if hasattr(self.memory_manager, 'conversation_turn_count'):
                # Update metrics to get latest values
                metrics = self.memory_manager.update_conversation_metrics(increment_turns=False)
                risk_level = "low"
                if metrics["turns"] > 50 or metrics["duration_minutes"] > 60:
                    risk_level = "high"
                elif metrics["turns"] > 30 or metrics["duration_minutes"] > 45:
                    risk_level = "medium"
                
                conversation_metrics = f"""
# Conversation Status
- Turn count: {metrics["turns"]}
- Duration: {metrics["duration_minutes"]:.1f} minutes
- Context window risk: {risk_level}
- Use /compact command if conversation is getting too long
"""
            
            # Add memory stats if available
            memory_stats = ""
            if hasattr(self.memory_manager, 'memory_stats'):
                memory_stats = "\n# Memory Status\n"
                # Only show key memory stats to avoid clutter
                key_stats = ['nodes_added', 'documents_saved', 'mind_maps_created', 'notes_added']
                for k in key_stats:
                    if k in self.memory_manager.memory_stats:
                        memory_stats += f"- {k}: {self.memory_manager.memory_stats[k]}\n"
            
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
            
            # Add mind maps if available
            mind_maps_section = ""
            if hasattr(self.memory_manager, 'mind_maps') and self.memory_manager.mind_maps:
                # Show only the most recently modified mind maps
                recent_maps = sorted(
                    self.memory_manager.mind_maps.values(),
                    key=lambda m: m.get("last_modified", 0),
                    reverse=True
                )[:2]
                
                if recent_maps:
                    mind_maps_section = "\n# Active Mind Maps\n"
                    for mind_map in recent_maps:
                        mind_maps_section += f"- {mind_map.get('title')} ({mind_map.get('metadata', {}).get('node_count', 0)} concepts)\n"
            
            # Add note about memory management
            memory_management = """
# Memory Management
- Leave SHORT, CONCISE notes about important information with memory_manager.add_agent_note()
- Track task status with memory_manager.log_task_status()
- Create mind maps for complex topics with memory_manager.create_mind_map()
- Add permanent knowledge to memory_manager.add_to_knowledge_base()
- Minimize file output in stdout - focus on showing only essential information
"""
            
            # Add persistent memory from previous sessions if available
            persistent_memory_section = ""
            try:
                if hasattr(self.memory_manager, 'get_session_persistent_memory'):
                    persistent_data = self.memory_manager.get_session_persistent_memory()
                    
                    if persistent_data and any(persistent_data.values()):
                        persistent_memory_section = "\n# Previous Session Context\n"
                        
                        # Add agent notes
                        if persistent_data.get("agent_notes"):
                            persistent_memory_section += "\n## Important Agent Notes\n"
                            for note in persistent_data["agent_notes"][:5]:  # Limit to top 5
                                persistent_memory_section += f"- {note.get('content', '')}\n"
                        
                        # Add task statuses
                        if persistent_data.get("task_statuses"):
                            persistent_memory_section += "\n## Recent Task Statuses\n"
                            for status in persistent_data["task_statuses"][:3]:  # Limit to top 3
                                persistent_memory_section += f"- {status.get('content', '')}\n"
                        
                        # Add mind maps
                        if persistent_data.get("mind_maps"):
                            persistent_memory_section += "\n## Active Mind Maps\n"
                            for mind_map in persistent_data["mind_maps"]:
                                persistent_memory_section += f"- {mind_map.get('title', '')} ({mind_map.get('nodes_count', 0)} concepts)\n"
                        
                        # Add knowledge base items
                        if persistent_data.get("knowledge_base"):
                            persistent_memory_section += "\n## Knowledge Base\n"
                            for item in persistent_data["knowledge_base"]:
                                truncated_content = item.get('content', '')
                                if len(truncated_content) > 100:
                                    truncated_content = truncated_content[:97] + "..."
                                persistent_memory_section += f"- {item.get('title', '')}: {truncated_content}\n"
            except Exception as e:
                logger.error(f"Error adding persistent memory to system prompt: {e}")
            
            # Combine all sections
            combined_prompt = f"{system_prompt}\n\n{identity_section}{system_info_section}{conversation_metrics}{persistent_memory_section}{memory_stats}{files_section}{tasks_section}{mind_maps_section}{memory_management}"
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
        """
        Print only the message content from the agent's response, plus any commands.
        Formats the output to be more concise and avoids showing file contents.
        """
        # Extract message tag content if present
        message_content = None
        message_match = re.search(r'<message>(.*?)</message>', content, re.DOTALL)
        if message_match:
            message_content = message_match.group(1).strip()
        
        # Extract commands for display
        commands = []
        for tag in self.command_extractor.COMMAND_TAGS:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, content, re.DOTALL)
            for match in matches:
                cmd = match.group(1).strip()
                # For bash commands, only show the first line or a shortened version
                if tag == "bash" and len(cmd.split('\n')) > 1:
                    cmd_first_line = cmd.split('\n')[0]
                    commands.append(f"$ {cmd_first_line}")
                else:
                    # Truncate long commands
                    if len(cmd) > 100:
                        cmd = cmd[:97] + "..."
                    commands.append(f"$ {cmd}")
        
        # Handle file operations specially - just show a summary
        file_ops = []
        for tag in self.command_extractor.FILE_OP_TAGS:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, content, re.DOTALL)
            for match in matches:
                cmd = match.group(1).strip()
                
                # Parse parameters to get file path
                params = {}
                try:
                    if cmd.strip().startswith('{') and cmd.strip().endswith('}'):
                        params = json.loads(cmd)
                    else:
                        # Try line-by-line parsing for key: value format
                        for line in cmd.split('\n'):
                            if ':' in line:
                                key, value = line.split(':', 1)
                                params[key.strip()] = value.strip()
                except:
                    pass
                
                # Create a concise summary based on operation type
                if tag == "view" and "file_path" in params:
                    file_ops.append(f"📄 Reading {params['file_path']}")
                elif tag == "edit" and "file_path" in params:
                    file_ops.append(f"✏️ Editing {params['file_path']}")
                elif tag == "replace" and "file_path" in params:
                    file_ops.append(f"🔄 Replacing {params['file_path']}")
                elif tag == "glob" and "pattern" in params:
                    file_ops.append(f"🔍 Finding files matching {params['pattern']}")
                elif tag == "grep" and "pattern" in params:
                    file_ops.append(f"🔍 Searching for '{params['pattern']}' in files")
                elif tag == "ls" and "path" in params:
                    file_ops.append(f"📁 Listing directory {params['path']}")
                else:
                    file_ops.append(f"{tag.upper()}: Operation on files")
                    
        # Extract thinking blocks for better context awareness
        thinking_blocks = self.command_extractor.extract_thinking(content)
        planning_blocks = self.command_extractor.extract_plan(content)
        
        # Print in a more compact way
        print("\n", end="")
        
        # Show agent's actual message first as it's most important
        if message_content:
            print(message_content.strip())
            print("")
        
        # Compact command display
        if commands:
            print("Commands:")
            for cmd in commands:
                print(f"  {cmd}")
            print("")
        
        # Show file operations
        if file_ops:
            print("File Operations:")
            for op in file_ops:
                print(f"  {op}")
            print("")
        
        # If nothing found in the structured format, fall back to printing the whole response
        if not message_content and not commands and not file_ops:
            # Strip XML tags for cleaner output
            clean_content = re.sub(r'<[^>]+>', '', content)
            print(clean_content.strip())
            
        # Update the conversation turn count in memory manager
        if hasattr(self.memory_manager, 'update_conversation_metrics'):
            self.memory_manager.update_conversation_metrics()

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
        """
        Generate a comprehensive summary of the current session with enhanced intelligence.
        This summary is used for both the user and for maintaining context between sessions.
        """
        try:
            # Extract all user messages
            user_msgs = [m['content'] for m in self.local_conversation_history if m.get('role') == 'user']
            
            # Extract all assistant messages
            assistant_msgs = [m['content'] for m in self.local_conversation_history if m.get('role') == 'assistant']
            
            # Get all reasoning blocks that help understand the session
            decisions = []
            plans = []
            summaries = []
            thinking = []
            for msg in assistant_msgs:
                decisions.extend(self.command_extractor.extract_decision(msg))
                plans.extend(self.command_extractor.extract_plan(msg))
                summaries.extend(self.command_extractor.extract_summary(msg))
                thinking.extend(self.command_extractor.extract_thinking(msg))
            
            # Extract commands executed (separate by type for better organization)
            commands_by_type = {}
            for msg in assistant_msgs:
                for tag in self.command_extractor.COMMAND_TAGS:
                    pattern = f"<{tag}>(.*?)</{tag}>"
                    matches = re.finditer(pattern, msg, re.DOTALL)
                    for match in matches:
                        cmd = match.group(1).strip().split('\n')[0]  # First line only
                        if tag not in commands_by_type:
                            commands_by_type[tag] = []
                        commands_by_type[tag].append(cmd)
            
            # Create a comprehensive summary
            summary_parts = []
            
            # Start with session metadata
            summary_parts.append("# Session Summary\n")
            summary_parts.append(f"Generated: {datetime.now().isoformat()}")
            summary_parts.append(f"Session ID: {self.agent_id}")
            summary_parts.append(f"Duration: {len(self.local_conversation_history)//2} turns")
            
            # Add initial task with the original request for context
            if user_msgs:
                summary_parts.append("\n## Initial Task")
                # More comprehensive initial task - it's important for continuity
                initial_task = user_msgs[0]
                # Keep more of the initial task if it's not too long
                if len(initial_task) > 500:
                    summary_parts.append(initial_task[:500] + "...")
                else:
                    summary_parts.append(initial_task)
            
            # Extract key insights from thinking blocks
            if thinking:
                insights = []
                for thought in thinking:
                    lines = thought.split('\n')
                    for line in lines:
                        line = line.strip()
                        if any(marker in line.lower() for marker in ['important', 'key insight', 'conclusion', 'critical']):
                            if line and len(line) > 10:
                                insights.append(line)
                
                if insights:
                    summary_parts.append("\n## Key Insights")
                    for insight in insights[:5]:  # Limit to 5 most important insights
                        summary_parts.append(f"- {insight}")
            
            # Key decisions with higher priority - they're important
            if decisions:
                summary_parts.append("\n## Key Decisions")
                for i, decision in enumerate(decisions[:3]):
                    # Format multi-line decisions
                    decision_text = decision.replace('\n', ' ').strip()
                    if len(decision_text) > 300:
                        decision_text = decision_text[:297] + "..."
                    summary_parts.append(f"{i+1}. {decision_text}")
            
            # Add task accomplishments if detected
            task_accomplishments = []
            for msg in assistant_msgs[-3:]:  # Look at last 3 messages for accomplishments
                lines = msg.split('\n')
                for line in lines:
                    line = line.strip()
                    if any(marker in line.lower() for marker in 
                          ['completed', 'finished', 'implemented', 'created', 'fixed', 'solved', 'built']):
                        if len(line) > 10 and not line.startswith('<') and not line.endswith('>'):
                            task_accomplishments.append(line)
            
            if task_accomplishments:
                summary_parts.append("\n## Accomplishments")
                for task in task_accomplishments[:5]:
                    summary_parts.append(f"- {task}")
            
            # Plans developed (structured as a list for clarity)
            if plans:
                summary_parts.append("\n## Plans")
                for plan in plans[:2]:  # Only include top 2 plans
                    # Format plans as bullet points if multi-line
                    plan_lines = plan.split('\n')
                    if len(plan_lines) > 1:
                        summary_parts.append("Plan steps:")
                        for line in plan_lines[:5]:  # Limit to first 5 steps
                            if line.strip():
                                summary_parts.append(f"- {line.strip()}")
                        if len(plan_lines) > 5:
                            summary_parts.append(f"- ...and {len(plan_lines) - 5} more steps")
                    else:
                        summary_parts.append(plan)
            
            # Key commands executed (organized by type)
            if commands_by_type:
                summary_parts.append("\n## Key Commands")
                for tag, cmds in commands_by_type.items():
                    # Only show a few examples of each command type
                    if cmds:
                        summary_parts.append(f"\n{tag.upper()} Commands:")
                        for cmd in cmds[:5]:  # Limit to 5 per type
                            summary_parts.append(f"- {cmd}")
                        if len(cmds) > 5:
                            summary_parts.append(f"- ...and {len(cmds) - 5} more {tag} commands")
            
            # Created/modified files (from working memory)
            if 'important_files' in self.working_memory and self.working_memory['important_files']:
                summary_parts.append("\n## Important Files")
                for file_path in self.working_memory['important_files']:
                    summary_parts.append(f"- {file_path}")
            
            # Final outcome - prioritize explicit summaries over last messages
            if summaries:
                summary_parts.append("\n## Results and Outcomes")
                summary_parts.append("\n".join(summaries[:2]))  # Limit to top 2 summaries
            elif assistant_msgs:
                # If no explicit summaries, use the last assistant message
                summary_parts.append("\n## Final Status")
                # Remove XML tags from the last message for cleaner summary
                last_msg = re.sub(r'<[^>]+>', '', assistant_msgs[-1])
                # Take a larger portion of the last message, it's important for continuity
                if len(last_msg) > 400:
                    summary_parts.append(last_msg[:400] + "...")
                else:
                    summary_parts.append(last_msg)
            
            # Generate recommendations for future sessions
            recommendations = []
            
            # Check for unfinished tasks
            if 'tasks' in self.working_memory:
                unfinished = [t for t in self.working_memory['tasks'] 
                             if t.get('status', '') not in ['completed', 'done']]
                if unfinished:
                    recommendations.append("Continue working on unfinished tasks from this session")
            
            # Check if any plans were not fully implemented
            if plans and not any(word in ' '.join(summaries).lower() 
                               for word in ['completed', 'finished', 'done', 'implemented']):
                recommendations.append("Complete implementation of plans from this session")
            
            # Add recommendations if any were generated
            if recommendations:
                summary_parts.append("\n## Recommendations for Next Session")
                for rec in recommendations:
                    summary_parts.append(f"- {rec}")
            
            # Combine all parts into a coherent summary
            full_summary = "\n".join(summary_parts)
            
            # Save the summary as an agent note for future reference
            try:
                if hasattr(self.memory_manager, 'add_agent_note'):
                    # Create a condensed version for the agent note (first 500 chars)
                    condensed = f"Session summary: {' '.join(summary_parts[:3])}..."
                    if len(condensed) > 500:
                        condensed = condensed[:497] + "..."
                    
                    self.memory_manager.add_agent_note(
                        condensed,
                        note_type="session_summary",
                        importance="high",
                        tags=["session", "summary", "important"]
                    )
                    
                    # Also save full details as a knowledge base item if long enough
                    if len(full_summary) > 300 and hasattr(self.memory_manager, 'add_to_knowledge_base'):
                        self.memory_manager.add_to_knowledge_base(
                            f"Session Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                            full_summary,
                            tags=["session", "summary", "history"]
                        )
            except Exception as note_error:
                logger.error(f"Error saving session summary as agent note: {note_error}")
            
            return full_summary
            
        except Exception as e:
            logger.error(f"Error generating enhanced session summary: {e}")
            # Create a fallback minimal summary
            try:
                fallback = f"Session completed at {datetime.now().isoformat()}\n"
                if self.local_conversation_history and len(self.local_conversation_history) > 1:
                    user_msgs = [m for m in self.local_conversation_history if m.get('role') == 'user']
                    if user_msgs:
                        fallback += f"Initial request: {user_msgs[0]['content'][:100]}...\n"
                    fallback += f"Total exchanges: {len(self.local_conversation_history) // 2}"
                return fallback
            except:
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

    async def add_human_context(self, additional_context: str):
        """
        Add human-provided context to the last assistant response and continue the conversation.
        This allows humans to pause the conversation and provide more context.
        
        Args:
            additional_context: The additional context provided by the human
        """
        if not self.last_assistant_response:
            logger.warning("No previous assistant response to add context to")
            return
            
        # Mark that we're paused for human context
        self.paused_for_human_context = True
        
        try:
            # Remove the last assistant message from history
            if self.local_conversation_history and self.local_conversation_history[-1].get('role') == 'assistant':
                last_assistant_msg = self.local_conversation_history.pop()
                original_content = last_assistant_msg['content']
                
                # Format the combined content with clear separation
                formatted_context = f"""
{original_content}

[HUMAN_ADDED_CONTEXT]
{additional_context}
[/HUMAN_ADDED_CONTEXT]
"""
                
                # Create a new message with combined content
                merged_msg = {
                    "role": "assistant", 
                    "content": formatted_context
                }
                
                # Add it back to the conversation history
                self.local_conversation_history.append(merged_msg)
                self.last_assistant_response = formatted_context
                
                # Record this pause and context addition in working memory
                if 'human_context_additions' not in self.working_memory:
                    self.working_memory['human_context_additions'] = []
                    
                self.working_memory['human_context_additions'].append({
                    'timestamp': datetime.now().isoformat(),
                    'context_added': additional_context,
                    'turn': len(self.local_conversation_history) // 2
                })
                
                # Also record in memory manager for persistence
                try:
                    self.memory_manager.save_document(
                        f"human_context_{int(time.time())}",
                        f"Human added context at turn {len(self.local_conversation_history) // 2}:\n\n{additional_context}",
                        tags=["human_context", "conversation", "pause"],
                        metadata={
                            "timestamp": time.time(),
                            "turn": len(self.local_conversation_history) // 2,
                            "content_length": len(additional_context)
                        }
                    )
                except Exception as e:
                    logger.error(f"Error saving human context addition to memory: {e}")
                
                # Log the context addition
                logger.info(f"Added human context of {len(additional_context)} chars to conversation")
                
            else:
                logger.warning("Cannot add context: Last message in history is not from assistant")
                
        except Exception as e:
            logger.error(f"Error adding human context: {e}")
        finally:
            # Reset the pause state
            self.paused_for_human_context = False
    
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

    async def compress_context(self, messages: List[Dict], token_limit: int = 16000, force: bool = False) -> List[Dict]:
        """
        Compress conversation context when it gets too large, with enhanced information prioritization.
        Implements intelligent summarization of earlier exchanges while keeping recent messages intact.
        
        Args:
            messages: List of conversation messages
            token_limit: Target token limit (approximate)
            force: Whether to force compression even if under token limit
            
        Returns:
            Compressed message list that fits within the token limit
        """
        # Simple and conservative estimate - each char is roughly 0.25 tokens
        estimated_tokens = sum(len(str(msg.get('content', ''))) for msg in messages) // 4
        
        if estimated_tokens <= token_limit and not force:
            return messages  # No compression needed
        
        try:
            # Record compression event
            compression_start = time.time()
            pre_compression_size = estimated_tokens
            
            # Keep system message, last 3 user exchanges, and summarize earlier parts
            system_messages = [msg for msg in messages if msg.get('role') == 'system']
            user_messages = [msg for msg in messages if msg.get('role') == 'user']
            assistant_messages = [msg for msg in messages if msg.get('role') == 'assistant']
            
            # Always keep system messages (they're important for context)
            kept_messages = system_messages.copy()
            
            # Identify and mark key information in messages before compressing
            # 1. Messages with high-value information (decisions, code, important findings)
            # 2. First message and messages establishing task context
            # 3. Recent messages that maintain continuity
            
            # Tag messages with their importance score
            scored_messages = []
            
            # First message gets high score (often contains initial task description)
            if user_messages:
                initial_msg = user_messages[0]
                scored_messages.append((initial_msg, 10, 0))  # (message, score, original_index)
            
            # Score each assistant message
            for i, msg in enumerate(assistant_messages):
                score = 0
                content = msg.get('content', '')
                
                # Check for key content types that indicate importance
                # Code blocks are high value
                if re.search(r'```[a-z]*\n[\s\S]*?\n```', content):
                    score += 5
                
                # Decision blocks are high value
                if len(self.command_extractor.extract_decision(content)) > 0:
                    score += 8
                
                # Planning blocks are high value
                if len(self.command_extractor.extract_plan(content)) > 0:
                    score += 7
                
                # Task definitions are high value
                if len(self.command_extractor.extract_tasks(content)) > 0:
                    score += 6
                
                # Command execution is medium value
                if len(re.findall(r'<(bash|python)>.*?</(bash|python)>', content, re.DOTALL)) > 0:
                    score += 4
                
                # Summary blocks are medium value
                if len(self.command_extractor.extract_summary(content)) > 0:
                    score += 5
                
                # Recent messages get a recency boost
                recency_boost = max(0, 5 - min(5, (len(assistant_messages) - i)))
                score += recency_boost
                
                # Store original index to maintain order
                original_index = messages.index(msg)
                scored_messages.append((msg, score, original_index))
            
            # Score each user message
            for i, msg in enumerate(user_messages[1:], 1):  # Skip the first message, already added
                score = 0
                content = msg.get('content', '')
                
                # Messages with code snippets are valuable
                if re.search(r'```[a-z]*\n[\s\S]*?\n```', content):
                    score += 5
                
                # Messages with direct questions are valuable
                if '?' in content:
                    score += 4
                
                # Messages with commands or instructions are valuable
                if any(cmd in content.lower() for cmd in ['create', 'make', 'implement', 'build', 'fix', 'update']):
                    score += 3
                
                # Recent messages get a recency boost
                recency_boost = max(0, 5 - min(5, (len(user_messages) - i)))
                score += recency_boost
                
                # Store original index to maintain order
                original_index = messages.index(msg)
                scored_messages.append((msg, score, original_index))
            
            # Sort by score (descending)
            scored_messages.sort(key=lambda x: x[1], reverse=True)
            
            # Determine how many exchanges to keep based on context size
            base_exchanges = 3
            if estimated_tokens > token_limit * 1.5:  # If severely over token limit
                exchanges_to_keep = 2  # Keep fewer messages
            elif estimated_tokens <= token_limit * 1.2:  # If only slightly over
                exchanges_to_keep = min(5, len(user_messages))  # May keep more messages
            else:
                exchanges_to_keep = base_exchanges
            
            # Keep most recent exchanges (user + assistant pairs) regardless of score
            # These maintain conversation continuity
            for i in range(1, exchanges_to_keep + 1):
                if i <= len(user_messages):
                    user_msg = user_messages[-i]
                    
                    # Check if already in kept_messages
                    if user_msg not in [m for m, _, _ in scored_messages[:exchanges_to_keep]]:
                        # Add with high score to ensure it's kept, but after the top scored messages
                        scored_messages.insert(exchanges_to_keep, 
                                             (user_msg, 100 - i, messages.index(user_msg)))
                    
                    if i <= len(assistant_messages):
                        asst_msg = assistant_messages[-i]
                        
                        # Check if already in kept_messages
                        if asst_msg not in [m for m, _, _ in scored_messages[:exchanges_to_keep*2]]:
                            # Add with high score to ensure it's kept
                            scored_messages.insert(exchanges_to_keep*2, 
                                                 (asst_msg, 100 - i, messages.index(asst_msg)))
            
            # Calculate how many high-value messages we can keep (based on token budget)
            # We want to keep about 70% of the token budget for the highest value messages
            token_target = token_limit * 0.7
            kept_tokens = sum(len(str(msg.get('content', ''))) for msg in system_messages) // 4
            
            # Add highest scored messages until we reach the target
            high_value_messages = []
            for msg, score, original_index in scored_messages:
                msg_tokens = len(str(msg.get('content', ''))) // 4
                if kept_tokens + msg_tokens <= token_target:
                    high_value_messages.append((msg, original_index))
                    kept_tokens += msg_tokens
                else:
                    # If we can't fit more high-value messages, stop
                    break
            
            # Sort by original order
            high_value_messages.sort(key=lambda x: x[1])
            
            # Add high-value messages to kept_messages
            for msg, _ in high_value_messages:
                if msg not in kept_messages:
                    kept_messages.append(msg)
            
            # Messages to summarize are ones not kept
            to_summarize = [m for m in messages if m not in kept_messages]
            
            if not to_summarize:
                return kept_messages  # No messages to summarize
            
            # Group messages to summarize by role
            user_to_summarize = [m['content'] for m in to_summarize if m.get('role') == 'user']
            assistant_to_summarize = [m['content'] for m in to_summarize if m.get('role') == 'assistant']
            
            # Get key information from agent notes if available
            agent_notes = []
            try:
                if hasattr(self.memory_manager, 'search_memory'):
                    agent_notes = self.memory_manager.search_memory(
                        "important", 
                        tags=["agent_notes", "important"], 
                        limit=5,
                        recency_boost=True
                    )
                    
                    # Additionally, get task-specific notes
                    if 'current_task' in self.working_memory:
                        task_notes = self.memory_manager.search_memory(
                            self.working_memory['current_task'], 
                            tags=["agent_notes"], 
                            limit=3,
                            recency_boost=True
                        )
                        # Combine without duplicates
                        existing_ids = set(note.get('id', '') for note in agent_notes)
                        for note in task_notes:
                            if note.get('id', '') not in existing_ids:
                                agent_notes.append(note)
            except Exception as note_error:
                logger.error(f"Error getting agent notes during compression: {note_error}")
            
            # Get knowledge base items
            knowledge_items = []
            try:
                if hasattr(self.memory_manager, 'search_memory'):
                    knowledge_items = self.memory_manager.search_memory(
                        "knowledge_base", 
                        tags=["knowledge_base", "permanent"],
                        limit=2,
                        recency_boost=False  # Knowledge items don't need recency bias
                    )
            except Exception as kb_error:
                logger.error(f"Error getting knowledge base items during compression: {kb_error}")
            
            # Create summary
            summary_parts = []
            
            # Add a clear header to indicate this is a summary
            summary_parts.append("## PREVIOUS CONVERSATION SUMMARY")
            summary_parts.append(f"(Compressed {len(to_summarize)} earlier messages at turn {self.memory_manager.conversation_turn_count})")
            
            # Add high-priority agent notes first
            if agent_notes:
                summary_parts.append("\n### Important Agent Notes")
                for note in agent_notes:
                    note_content = note.get('content', '').strip()
                    if len(note_content) > 200:
                        note_content = note_content[:197] + "..."
                    summary_parts.append(f"- {note_content}")
            
            # Add knowledge base items for continuity
            if knowledge_items:
                summary_parts.append("\n### Knowledge Base")
                for item in knowledge_items:
                    content = item.get('content', '').strip()
                    if len(content) > 200:
                        content = content[:197] + "..."
                    summary_parts.append(f"- **{item.get('title', '')}**: {content}")
            
            # Extract important mind maps if available
            mind_maps = []
            try:
                if hasattr(self.memory_manager, 'search_mind_maps'):
                    # Get most relevant mind maps to current context
                    if user_messages and len(user_messages[-1]['content']) > 10:
                        query = user_messages[-1]['content'][:100]  # Use latest user message
                        mind_maps = self.memory_manager.search_mind_maps(query, limit=1)
                        
                        # If no results based on latest message, try with current task
                        if not mind_maps and 'current_task' in self.working_memory:
                            task_query = self.working_memory['current_task']
                            mind_maps = self.memory_manager.search_mind_maps(task_query, limit=1)
            except Exception as mind_map_error:
                logger.error(f"Error getting mind maps during compression: {mind_map_error}")
            
            # Include mind map summary if available
            if mind_maps and hasattr(self.memory_manager, 'extract_mind_map_summary'):
                try:
                    map_id = mind_maps[0]['id']
                    map_summary = self.memory_manager.extract_mind_map_summary(map_id)
                    # Only include first part to save tokens
                    if len(map_summary) > 500:
                        map_lines = map_summary.split('\n')
                        short_summary = '\n'.join(map_lines[:10]) + "\n(mind map truncated to save context space)"
                        summary_parts.append(f"\n{short_summary}")
                    else:
                        summary_parts.append(f"\n{map_summary}")
                except Exception as e:
                    logger.error(f"Error extracting mind map summary: {e}")
            
            # Summarize user messages with refined extraction
            if user_to_summarize:
                summary_parts.append("\n### User Requests & Questions")
                
                # Extract key questions and commands
                questions = []
                commands = []
                requirements = []
                
                for msg in user_to_summarize:
                    # Look for question marks or implied questions
                    lines = msg.split('\n')
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        # Identify command-like statements
                        if line.startswith('/') or any(cmd in line.lower() for cmd in 
                                                     ['run', 'execute', 'install', 'create', 'generate', 
                                                      'implement', 'build', 'make']):
                            commands.append(line)
                        # Identify questions
                        elif '?' in line or any(starter in line.lower() for starter in 
                                              ['how ', 'what ', 'when ', 'where ', 'why ', 'can you', 'please ']):
                            questions.append(line)
                        # Identify requirements or specifications
                        elif any(req in line.lower() for req in 
                                ['need', 'require', 'must', 'should', 'important', 'ensure', 'make sure']):
                            requirements.append(line)
                
                # Add prioritized content
                if commands:
                    summary_parts.append("Key commands requested:")
                    for i, cmd in enumerate(commands[:3]):  # Limit to 3 most important
                        summary_parts.append(f"- {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
                
                if questions:
                    summary_parts.append("Key questions asked:")
                    for i, q in enumerate(questions[:3]):  # Limit to 3 most important
                        summary_parts.append(f"- {q[:100]}{'...' if len(q) > 100 else ''}")
                
                if requirements:
                    summary_parts.append("Key requirements specified:")
                    for i, req in enumerate(requirements[:3]):  # Limit to 3 most important
                        summary_parts.append(f"- {req[:100]}{'...' if len(req) > 100 else ''}")
                
                # Add general topics as fallback
                if not commands and not questions and not requirements:
                    summary_parts.append("General topics discussed:")
                    topic_summary = "; ".join([m[:40] + ('...' if len(m) > 40 else '') for m in user_to_summarize[:2]])
                    summary_parts.append(f"- {topic_summary}")
            
            # Summarize assistant actions with focus on important operations
            if assistant_to_summarize:
                summary_parts.append("\n### Agent Actions & Decisions")
                
                # Extract key information in order of priority
                
                # 1. Extract decision blocks (highest priority)
                decisions = []
                for msg in assistant_to_summarize:
                    decisions.extend(self.command_extractor.extract_decision(msg))
                
                # 2. Extract plans 
                plans = []
                for msg in assistant_to_summarize:
                    plans.extend(self.command_extractor.extract_plan(msg))
                
                # 3. Extract tasks and subtasks (important for continuity)
                tasks = []
                for msg in assistant_to_summarize:
                    tasks.extend(self.command_extractor.extract_tasks(msg))
                
                # 4. Extract command patterns executed (important for continuity)
                all_commands = []
                for msg in assistant_to_summarize:
                    for tag in CommandExtractor.COMMAND_TAGS:
                        pattern = f"<{tag}>(.*?)</{tag}>"
                        matches = re.finditer(pattern, msg, re.DOTALL)
                        for match in matches:
                            cmd = match.group(1).strip().split('\n')[0][:40]  # Just first line, limited length
                            all_commands.append(f"{tag}: {cmd}...")
                
                # 5. Extract key insights from reasoning blocks
                insights = []
                thinking_patterns = ["<thinking>(.*?)</thinking>"]
                for msg in assistant_to_summarize:
                    for pattern in thinking_patterns:
                        matches = re.finditer(pattern, msg, re.DOTALL)
                        for match in matches:
                            content = match.group(1).strip()
                            # Extract key sentences with importance markers
                            sentences = re.split(r'[.!?]\s+', content)
                            for sentence in sentences:
                                if len(sentence) > 10 and len(sentence) < 100:
                                    if any(kw in sentence.lower() for kw in ['important', 'critical', 'key', 'must', 'should']):
                                        insights.append(sentence)
                
                # 6. Extract code blocks
                code_blocks = []
                for msg in assistant_to_summarize:
                    # Match code blocks with language specifier
                    code_pattern = r'```([a-z]*)\n([\s\S]*?)\n```'
                    matches = re.finditer(code_pattern, msg, re.DOTALL)
                    for match in matches:
                        lang, code = match.groups()
                        # Only keep short, important snippets
                        if len(code.split('\n')) <= 5:
                            if lang:
                                code_blocks.append(f"{lang}: {code.strip()[:100]}...")
                            else:
                                code_blocks.append(f"Code: {code.strip()[:100]}...")
                
                # Add the extracted information in priority order
                # Add decisions (highest priority)
                if decisions:
                    summary_parts.append("Key decisions made:")
                    for decision in decisions[:2]:  # Limit to 2 most important decisions
                        # Truncate long decisions
                        if len(decision) > 150:
                            decision = decision[:147] + "..."
                        summary_parts.append(f"- {decision}")
                
                # Add tasks
                if tasks:
                    summary_parts.append("Tasks identified:")
                    for task in tasks[:2]:  # Limit to 2 most important tasks
                        # Format and truncate long tasks
                        if len(task) > 150:
                            task = task[:147] + "..."
                        summary_parts.append(f"- {task}")
                
                # Add plans
                if plans:
                    summary_parts.append("Planning:")
                    for plan in plans[:1]:  # Just the most recent plan
                        # Format and truncate long plans
                        plan_lines = plan.split('\n')
                        if len(plan_lines) > 5:
                            summary_parts.append(f"- {'. '.join(plan_lines[:5])}...")
                        else:
                            summary_parts.append(f"- {plan}")
                
                # Add commands executed
                if all_commands:
                    summary_parts.append("Key commands executed:")
                    for cmd in all_commands[:3]:  # Limit to most important commands
                        summary_parts.append(f"- {cmd}")
                
                # Add code snippets if available
                if code_blocks and len(summary_parts) < 30:  # Only add if summary not too long already
                    summary_parts.append("Important code snippets:")
                    for code in code_blocks[:2]:  # Limit to 2 code blocks
                        summary_parts.append(f"- {code}")
                
                # Add key insights if space allows
                if insights and len(summary_parts) < 30:  # Only add if summary not too long already
                    summary_parts.append("Key insights:")
                    for insight in insights[:2]:  # Limit to 2 key insights
                        summary_parts.append(f"- {insight}")
            
            # Add important context from working memory (focus on current task)
            if self.working_memory:
                # Be selective about what working memory to include
                important_keys = ['current_task', 'important_files', 'tasks']
                has_important_items = any(key in self.working_memory for key in important_keys)
                
                if has_important_items:
                    summary_parts.append("\n### Current Context")
                    
                    # Add current task if available (highest priority)
                    if 'current_task' in self.working_memory:
                        summary_parts.append(f"Current task: {self.working_memory['current_task']}")
                    
                    # Add tasks in progress if available
                    if 'tasks' in self.working_memory and self.working_memory['tasks']:
                        tasks_to_show = min(2, len(self.working_memory['tasks']))
                        if tasks_to_show > 0:
                            # Show only active tasks
                            active_tasks = [t for t in self.working_memory['tasks'] 
                                           if t.get('status', '') not in ['completed', 'done']]
                            if active_tasks:
                                summary_parts.append("Active tasks:")
                                for task in active_tasks[:tasks_to_show]:
                                    summary_parts.append(f"- {task.get('title', 'Untitled task')} (Status: {task.get('status', 'pending')})")
                    
                    # Add important files if tracked (limited set)
                    if 'important_files' in self.working_memory and self.working_memory['important_files']:
                        files_to_show = min(3, len(self.working_memory['important_files']))
                        if files_to_show > 0:
                            summary_parts.append("Important files:")
                            for file in self.working_memory['important_files'][:files_to_show]:
                                summary_parts.append(f"- {file}")
            
            # Add a note about compression effects
            summary_parts.append(f"\nNote: {len(to_summarize)} messages were compressed to save context space.")
            summary_parts.append(f"Remember to use memory_manager.add_agent_note() for important information to improve context retention across compressions.")
            
            # Combine all summary parts and ensure it's not too large
            summary = "\n".join(summary_parts)
            
            # Record this compression in memory for future reference
            try:
                # Enhanced logging of compression with more details
                self.memory_manager.add_agent_note(
                    f"Compressed {len(to_summarize)} messages at turn {self.memory_manager.conversation_turn_count}. " +
                    f"Keeping {len(kept_messages)} messages including {len(high_value_messages)} high-priority messages based on content value.",
                    note_type="compression", 
                    importance="normal",
                    tags=["memory_management", "compression", "context_window"]
                )
                
                # Also record the state of tasks or topics before compression
                if 'current_task' in self.working_memory:
                    self.memory_manager.add_agent_note(
                        f"Task state before compression: {self.working_memory['current_task']}",
                        note_type="task_state",
                        importance="high",
                        tags=["compression", "task_continuity"]
                    )
            except Exception as note_error:
                logger.error(f"Error adding compression note: {note_error}")
                
            # Create a document version of this summary for future reference
            summary_doc_id = f"context_summary_{int(time.time())}"
            
            # Add session ID if available
            metadata = {
                "original_messages": len(messages),
                "kept_messages": len(kept_messages),
                "summarized_messages": len(to_summarize),
                "original_tokens": pre_compression_size,
                "turn_count": getattr(self.memory_manager, "conversation_turn_count", 0),
                "high_value_messages": len(high_value_messages)
            }
            
            if 'session_id' in self.working_memory:
                metadata["session_id"] = self.working_memory['session_id']
            
            self.memory_manager.save_document(
                summary_doc_id,
                summary,
                tags=["summary", "context", "compression", "session_state"],
                metadata=metadata
            )
            
            # Add the summary as a system message at the start
            kept_messages.insert(0 if not system_messages else 1, 
                               {"role": "system", "content": summary})
            
            # Log compression stats
            post_size = sum(len(str(msg.get('content', ''))) for msg in kept_messages) // 4
            compression_time = time.time() - compression_start
            compression_percentage = 100 - (post_size / pre_compression_size * 100)
            logger.info(f"Context compressed from {pre_compression_size} to {post_size} tokens ({compression_percentage:.1f}% reduction) in {compression_time:.2f}s")
            
            # Print compression stats if this was a forced compression (from /compact command)
            if force:
                print(f"✅ Context compressed: {pre_compression_size} → {post_size} tokens ({compression_percentage:.1f}% reduction)")
                print(f"Compressed {len(to_summarize)} messages, preserving {len(kept_messages)} messages including {len(high_value_messages)} high-priority messages.")
                print(f"Essential context has been preserved, including {len(agent_notes)} agent notes and continuity information.")
            
            return kept_messages
            
        except Exception as e:
            logger.error(f"Error during context compression: {e}")
            # More robust fallback - keep system message and last few exchanges
            try:
                system_msgs = [msg for msg in messages if msg.get('role') == 'system']
                non_system_msgs = [msg for msg in messages if msg.get('role') != 'system']
                # Keep last 10 non-system messages
                fallback_msgs = system_msgs + non_system_msgs[-10:] if len(non_system_msgs) > 10 else non_system_msgs
                
                # Log the fallback
                logger.warning("Using fallback compression due to error in main compression logic")
                
                # Record this in memory
                try:
                    self.memory_manager.add_agent_note(
                        "Warning: Used fallback compression due to error in main compression logic. Some context may be lost.",
                        note_type="compression_error",
                        importance="high",
                        tags=["error", "compression", "context_window"]
                    )
                except:
                    pass
                
                return fallback_msgs
            except:
                # Ultimate fallback
                logger.error("Critical compression failure - using minimal fallback")
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
                        # Check if this command should be executed in interactive mode
                        interactive_cmd = (cmd_type == 'bash' and 
                                          any(pkg_cmd in cmd_content for pkg_cmd in [
                                              'apt', 'apt-get', 'npm', 'pip install', 'pip3 install', 
                                              'gem', 'brew', 'yum', 'dnf', 'pacman'
                                          ]))
                        
                        stdout, stderr, code = await self.system_control.execute_command(
                            cmd_type, 
                            cmd_content, 
                            interactive=interactive_cmd,
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
            
        
