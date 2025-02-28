import asyncio
import logging
import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

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
    
    @staticmethod
    def extract_commands(response: str) -> List[Tuple[str, str]]:
        """Extract commands from response"""
        commands = []
        for tag in CommandExtractor.COMMAND_TAGS:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, response, re.DOTALL)
            for match in matches:
                command = match.group(1).strip()
                if command:
                    commands.append((tag, command))
        return commands
    
    @staticmethod
    def extract_thinking(response: str) -> List[str]:
        """Extract thinking blocks from response"""
        pattern = f"<{CommandExtractor.THINKING_TAG}>(.*?)</{CommandExtractor.THINKING_TAG}>"
        matches = re.finditer(pattern, response, re.DOTALL)
        return [
            match.group(1).strip() for match in matches
        ]

    @staticmethod
    def extract_heredocs(response: str) -> List[Dict[str, str]]:
        """Extract heredoc blocks from response text"""
        heredocs = []
        current_doc = None
        content_lines = []
        
        for line in response.split('\n'):
            if line.strip().startswith('cat << EOF >'):
                # Start new heredoc
                if current_doc:
                    heredocs.append({
                        'filename': current_doc,
                        'content': '\n'.join(content_lines)
                    })
                    content_lines = []
                # Extract filename
                current_doc = line.strip().split('>')[1].strip()
                continue
                
            if line.strip() == 'EOF' and current_doc:
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
        return lower_cmd in exit_cmds


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
        self.system_control = SystemControl()
        self.task_manager = TaskManager(self.memory_path)
        self.session_manager = session_manager or SessionManager(self.memory_path, self.memory_manager)

        # Seed memory if vector_index doesn't exist
        if not (self.memory_path / "vector_index").exists():
            self.memory_manager.save_document(
                "system_guide",
                Path("config/system_prompt.md").read_text()
            )

        self.llm = get_llm_client(model, api_key)
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.command_extractor = CommandExtractor()
        self.should_exit = False
        self.command_history = []
        self.heartbeat_task = None
        self.test_mode = test_mode

        # Local conversation history for multi-turn dialogues
        # Each element is a dict like: {"role": "user"/"assistant"/"system", "content": "..."}
        self.local_conversation_history: List[Dict[str, str]] = []

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
            print("\nInitializing new session...")
            # Start heartbeat task for periodic state saving
            self.heartbeat_task = asyncio.create_task(self.heartbeat())

            # Start a new session in session manager
            # Typically, you can specify shell, environment, etc. For now, keep it minimal.
            env = dict(os.environ)
            self.session_manager.start_session(
                shell_preference="bash",
                working_directory=str(Path.cwd()),
                environment=env
            )

            # Add system message
            system_msg = {"role": "system", "content": system_prompt}
            self.local_conversation_history.append(system_msg)

            # Add initial user message (the "task" given)
            user_msg = {"role": "user", "content": initial_prompt}
            self.local_conversation_history.append(user_msg)

            # Multi-turn loop
            while not self.should_exit:
                # Get LLM response (assistant message)
                response = await self.llm.get_response(
                    prompt=None,
                    system=None,
                    conversation_history=self.local_conversation_history,
                    tool_usage=False
                )
                if not response:
                    logger.warning("No response from LLM.")
                    break

                # Store assistant message
                assistant_msg = {"role": "assistant", "content": response}
                self.local_conversation_history.append(assistant_msg)
                self._print_response(response)

                # Extract and store chain of thought (thinking)
                thinking_blocks = self.command_extractor.extract_thinking(response)
                if thinking_blocks:
                    self.memory_manager.save_document(
                        "reasoning",
                        "\n\n".join(thinking_blocks),
                        tags=["chain_of_thought"]
                    )

                # Process potential heredocs
                await self.process_heredocs(response)

                # Extract commands
                commands = self.command_extractor.extract_commands(response)
                if not commands:
                    # If no commands, check if there's an explicit exit or session end
                    # We can also scan the raw text for "session_end" or a stand-alone "done"
                    # But for now let's see if there's some other condition
                    if "session_end" in response.lower():
                        print("Agent declared session end.")
                        self.should_exit = True
                        break
                    # Otherwise continue to next turn
                    # Provide a minimal output to simulate "OK" from environment
                    next_user_msg = {
                        "role": "user",
                        "content": "(No commands found - continuing...)"
                    }
                    self.local_conversation_history.append(next_user_msg)
                    continue

                # If there are commands, let's execute them
                all_outputs = []
                for cmd_type, cmd_content in commands:
                    if self.command_extractor.is_exit_command(cmd_type, cmd_content):
                        print("Agent used an exit command. Ending session.")
                        self.should_exit = True
                        break

                    # Actually execute the commands
                    if self.test_mode:
                        # In test mode, we don't really execute
                        output = f"[TEST MODE] Would have executed {cmd_type} command: {cmd_content}"
                        print(output)
                        all_outputs.append(output)
                        # Log to memory manager
                        self.memory_manager.add_command_to_history(cmd_content, cmd_type, success=True)
                    else:
                        stdout, stderr, code = await self.system_control.execute_command(cmd_type, cmd_content)
                        # Save command usage
                        self.memory_manager.add_command_to_history(cmd_content, cmd_type, code == 0)
                        # Merge outputs
                        if code != 0:
                            logger.warning(f"Command failed with exit code {code}")
                        combined_output = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}\nEXIT CODE: {code}"
                        all_outputs.append(combined_output)

                    if self.should_exit:
                        break

                # Provide the combined output as the next 'user' message for the agent
                if all_outputs and not self.should_exit:
                    combined_message = "\n\n".join(all_outputs)
                    next_user_msg = {
                        "role": "user",
                        "content": combined_message
                    }
                    self.local_conversation_history.append(next_user_msg)

            if self.should_exit:
                print("\nSession ended by agent.")
            else:
                print("\nSession completed naturally or stopped by empty response.")

        except Exception as e:
            logger.error(f"Run failed: {e}")
            raise
        finally:
            print("\nCleaning up...")
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
            self.cleanup()

    async def process_heredocs(self, response: str) -> None:
        """Process and save heredoc content to files"""
        heredocs = self.command_extractor.extract_heredocs(response)
        for doc in heredocs:
            try:
                filepath = Path(doc['filename'])
                filepath.parent.mkdir(parents=True, exist_ok=True)
                with open(filepath, 'w') as f:
                    f.write(doc['content'])
                logger.info(f"Created file: {filepath}")
            except Exception as e:
                logger.error(f"Error creating file {doc['filename']}: {e}")

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
            'sessions'
        ]
        for dir_name in dirs:
            (self.memory_path / dir_name).mkdir(parents=True, exist_ok=True)

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

        data_to_save = {
            "conversation": self.local_conversation_history,
            "ended_at": datetime.now().isoformat()
        }

        try:
            with open(session_path, "w") as f:
                json.dump(data_to_save, f, indent=2)
            logger.info(f"Session archived to {session_path}")
        except Exception as e:
            logger.error(f"Error writing session archive: {e}")

        try:
            conversation_id = f"session_{timestamp}"
            self.memory_manager.save_conversation(
                conversation_id,
                messages=self.local_conversation_history,
                metadata={"archived_at": datetime.now().isoformat()}
            )
            logger.info(f"Session also saved in memory graph as conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error saving session to memory graph: {e}")

    def cleanup(self):
        """Cleanup resources and save state"""
        try:
            history_path = self.memory_path / "state/command_history.json"
            with open(history_path, 'w') as f:
                json.dump(self.command_history, f, indent=2)
            self.system_control.cleanup()
            # Archive the final session conversation
            self.archive_session()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def heartbeat(self):
        """Auto-save state every 5 minutes"""
        while not self.should_exit:
            self._save_state()
            await asyncio.sleep(300)

    def _save_state(self):
        """Save critical state information periodically"""
        state = {
            "tasks": self.task_manager.active_tasks,
            "environment": dict(os.environ),
            "last_commands": self.command_history[-5:],
            "session_summary": self.last_session_summary
        }
        self.memory_manager.save_document("system_state", json.dumps(state))

    async def compress_context(self, messages: List[Dict]) -> List[Dict]:
        """Keep conversation under ~4k tokens (placeholder for possible context compression)"""
        if len(str(messages)) > 3500:
            relevant_memories = self.memory_manager.search_memory(
                "Recent important system changes"
            )
            return [{"role": "system", "content": f"Relevant memories: {relevant_memories}"}]
        return messages
