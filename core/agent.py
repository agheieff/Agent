# agent.py
import asyncio
import logging
import os
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from datetime import datetime
import json

# Configure logging - file handler gets everything, console gets filtered output
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
    """Autonomous agent with improved session handling and command execution"""
    def __init__(self, api_key: str, system_prompt_path: Path = Path("memory/config/system_prompt.txt")):
        if not api_key:
            raise ValueError("API key required")
            
        self.llm = AnthropicClient(api_key)
        self.memory_path = Path("memory")
        self.system_prompt = self._load_system_prompt(system_prompt_path)
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self._setup_storage()

    def _setup_storage(self):
        """Ensure required directories exist"""
        dirs = [
            'conversations',
            'logs',
            'summaries',
            'config'
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

            # Only log command execution, don't print to console
            logger.info(f"Command executed: {command}")
            if result.stderr:
                logger.warning(f"Command stderr: {result.stderr}")
            
            return result

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return CommandResult("", str(e), 1)

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from response text"""
        commands = []
        in_block = False
        current_cmd = []
        
        for line in response.split('\n'):
            stripped = line.strip()
            
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
                    commands.append(' '.join(current_cmd))
                    current_cmd = []
                    
        return [cmd for cmd in commands if cmd]

    async def think_and_act(self, initial_prompt: str) -> None:
        """Main conversation loop with better output control"""
        # Start with system context, last session summary, and initial prompt
        messages = []
        
        if self.last_session_summary:
            messages.append({
                "role": "system",
                "content": f"Last session summary:\n{self.last_session_summary}"
            })
        
        messages.append({"role": "user", "content": initial_prompt})
        
        try:
            while True:
                response = await self.llm.get_response(
                    "",
                    self.system_prompt,
                    messages
                )
                
                if not response:
                    logger.error("Failed to get LLM response")
                    break

                # Print only Claude's response
                self.print_response(response)
                messages.append({"role": "assistant", "content": response})

                # Execute commands silently
                commands = self.extract_commands(response)
                for cmd in commands:
                    result = await self.execute_command(cmd)
                    if result.output:
                        messages.append({"role": "user", "content": result.output})

                # Check for completion
                if self._is_conversation_complete(response):
                    # Save summary for next session
                    if "Summary:" in response:
                        summary = response.split("Summary:")[1].strip()
                        self._save_session_summary(summary)
                    break

        except KeyboardInterrupt:
            logger.info("Session interrupted by user")
        except Exception as e:
            logger.error(f"Session error: {e}")
            raise

    def _is_conversation_complete(self, response: str) -> bool:
        """Check if conversation is complete"""
        return any(phrase in response.lower() for phrase in [
            "task complete",
            "finished",
            "all done",
            "completed successfully"
        ])

    async def run(self, initial_prompt: str) -> None:
        """Run agent with error handling"""
        try:
            await self.think_and_act(initial_prompt)
        except Exception as e:
            logger.error(f"Run failed: {e}")
            raise
