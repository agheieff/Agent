import asyncio
import logging
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from core.llm_client import get_llm_client
from core.memory_manager import MemoryManager
from core.system_control import SystemControl

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)

# Only show user-relevant output to console
console_handler = logging.getLogger().handlers[1]
console_handler.setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class CommandResult:
    """Structured command execution results"""
    def __init__(self, stdout: str, stderr: str, code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.code = code
        self.success = code == 0

    @property
    def output(self) -> str:
        return self.stdout if self.stdout else self.stderr

class AutonomousAgent:
    """Enhanced autonomous agent with improved capabilities"""
    def __init__(self, api_key: str, model: str = "anthropic"):
        if not api_key:
            raise ValueError("API key required")
            
        self.llm = get_llm_client(model, api_key)
        self.memory_path = Path("memory")
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.system_control = SystemControl()
        self.memory_manager = MemoryManager()
        self._setup_storage()
        self.should_exit = False

    def _setup_storage(self):
        """Ensure required directories exist"""
        dirs = [
            'conversations',
            'logs',
            'summaries',
            'config',
            'scripts',
            'data',
            'temp'
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

    def print_response(self, content: str):
        """Print agent's response with clear formatting"""
        print("\n=== CLAUDE ===")
        print(content)
        print("=============")

    async def execute_command(self, command: str) -> CommandResult:
        """Execute a system command with better error handling"""
        try:
            # Handle exit command
            if command.strip().lower() in ['exit', 'quit', 'bye']:
                self.should_exit = True
                return CommandResult("Exiting session...", "", 0)

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            result = CommandResult(
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
                process.returncode
            )

            logger.info(f"Command executed: {command}")
            if result.stderr:
                logger.warning(f"Command stderr: {result.stderr}")
            
            return result

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return CommandResult("", str(e), 1)

    def extract_heredocs(self, response: str) -> List[Dict[str, str]]:
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

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from response text with enhanced capabilities"""
        commands = []
        in_block = False
        current_cmd = []
        in_heredoc = False
        
        for line in response.split('\n'):
            stripped = line.strip()
            
            # Check for exit command
            if stripped.lower() in ['exit', 'quit', 'bye']:
                commands.append(stripped)
                continue

            # Handle heredoc start
            if stripped.startswith('cat << EOF >'):
                in_heredoc = True
                current_cmd.append(line)
                continue
                
            # Handle heredoc content and end
            if in_heredoc:
                current_cmd.append(line)
                if stripped == 'EOF':
                    in_heredoc = False
                    commands.append('\n'.join(current_cmd))
                    current_cmd = []
                continue
            
            # Handle code blocks
            if stripped.startswith('```'):
                if in_block:
                    if current_cmd:
                        commands.append(' '.join(current_cmd))
                        current_cmd = []
                    in_block = False
                else:
                    in_block = True
                continue
                
            if in_block and stripped and not stripped.startswith('#'):
                if stripped.endswith('\\'):
                    current_cmd.append(stripped[:-1].strip())
                else:
                    current_cmd.append(stripped)
                    if not any(cmd.endswith('\\') for cmd in current_cmd):
                        commands.append(' '.join(current_cmd))
                        current_cmd = []
                    
        return [cmd for cmd in commands if cmd]

    async def process_heredocs(self, response: str) -> None:
        """Process and save heredoc content to files"""
        heredocs = self.extract_heredocs(response)
        for doc in heredocs:
            try:
                filepath = Path(doc['filename'])
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                with open(filepath, 'w') as f:
                    f.write(doc['content'])
                    
                logger.info(f"Created file: {filepath}")
            except Exception as e:
                logger.error(f"Error creating file {doc['filename']}: {e}")

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        """Enhanced main conversation loop"""
        messages = []
        
        if self.last_session_summary:
            messages.append({
                "role": "system",
                "content": f"Last session summary:\n{self.last_session_summary}"
            })
        
        messages.append({"role": "user", "content": initial_prompt})
        
        try:
            while not self.should_exit:
                response = await self.llm.get_response(
                    "",
                    system_prompt,
                    messages
                )
                
                if not response:
                    logger.error("Failed to get LLM response")
                    break

                self.print_response(response)
                messages.append({"role": "assistant", "content": response})

                # Process heredocs first
                await self.process_heredocs(response)

                # Execute commands
                commands = self.extract_commands(response)
                for cmd in commands:
                    if cmd.strip().lower() in ['exit', 'quit', 'bye']:
                        self.should_exit = True
                        print("\nExiting session...")
                        break
                        
                    if not cmd.startswith('cat << EOF'):
                        result = await self.execute_command(cmd)
                        if result.output:
                            messages.append({"role": "user", "content": result.output})

                # Allow user input for continuation
                if not self.should_exit:
                    user_input = input("\nPress Enter to continue or type 'exit' to end session: ").strip()
                    if user_input.lower() in ['exit', 'quit', 'bye']:
                        self.should_exit = True
                    elif user_input:
                        messages.append({"role": "user", "content": user_input})

                # Check for completion or exit
                if self.should_exit or self._is_conversation_complete(response):
                    if "Summary:" in response:
                        summary = response.split("Summary:")[1].strip()
                        self._save_session_summary(summary)
                    break

        except KeyboardInterrupt:
            logger.info("Session interrupted by user")
            self.should_exit = True
        except Exception as e:
            logger.error(f"Session error: {e}")
            raise

    def _is_conversation_complete(self, response: str) -> bool:
        """Check if conversation is complete"""
        completion_phrases = [
            "task complete",
            "finished",
            "all done",
            "completed successfully",
            "goodbye",
            "session ended"
        ]
        return any(phrase in response.lower() for phrase in completion_phrases)

    async def run(self, initial_prompt: str, system_prompt: str) -> None:
        """Run agent with enhanced error handling"""
        try:
            print("\nStarting agent session...")
            print("Type 'exit', 'quit', or 'bye' at any time to end the session")
            print("Press Ctrl+C to force quit")
            print("\nInitializing...")
            
            await self.think_and_act(initial_prompt, system_prompt)
            
            if self.should_exit:
                print("\nSession ended by user")
            else:
                print("\nSession completed naturally")
                
        except Exception as e:
            logger.error(f"Run failed: {e}")
            raise
        finally:
            print("\nCleaning up...")
            # Add any cleanup code here if needed

    def cleanup(self):
        """Cleanup resources and save state"""
        try:
            # Save any pending state
            if self.current_conversation_id:
                self.memory_manager.save_conversation(
                    self.current_conversation_id,
                    []  # Add any pending messages here
                )
            
            # Clean up temp directory
            temp_dir = self.memory_path / "temp"
            if temp_dir.exists():
                for file in temp_dir.iterdir():
                    try:
                        file.unlink()
                    except Exception as e:
                        logger.error(f"Error cleaning up {file}: {e}")
                        
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
