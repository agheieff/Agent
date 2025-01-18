import asyncio
import logging
import os
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from datetime import datetime
import json
from dataclasses import dataclass
from enum import Enum

# Configure logging with custom formatter to control output
class OutputFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.WARNING  # Only show warnings and errors

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),  # Full logging to file
        logging.StreamHandler()  # Filtered logging to console
    ]
)

console_handler = logging.getLogger().handlers[1]
console_handler.addFilter(OutputFilter())
logger = logging.getLogger(__name__)

@dataclass
class CommandResult:
    """Minimal command execution results"""
    stdout: str
    stderr: str
    code: int
    
    @property
    def output(self) -> str:
        """Get relevant output, preferring stdout"""
        return self.stdout if self.stdout else self.stderr

class ConversationStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"

class AutonomousAgent:
    """Autonomous agent with controlled output"""
    def __init__(self, api_key: str, base_path: Path = Path("memory"),
                 quiet_mode: bool = True):
        if not api_key:
            raise ValueError("API key required")
            
        self.llm = AnthropicClient(api_key)
        self.base_path = base_path
        self.current_conversation_id = None
        self.quiet_mode = quiet_mode
        self._setup_storage()

    def _setup_storage(self):
        """Initialize storage directories"""
        dirs = ['conversations', 'context', 'backups']
        for dir_name in dirs:
            (self.base_path / dir_name).mkdir(parents=True, exist_ok=True)

    def _print(self, message: str, level: str = "info"):
        """Controlled output based on quiet_mode"""
        if not self.quiet_mode or level in ["warning", "error"]:
            print(message)
        getattr(logger, level)(message)

    async def execute_command(self, command: str) -> CommandResult:
        """Execute system command with minimal output"""
        try:
            self._print(f"Executing: {command}", "debug")
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            return CommandResult(
                stdout=stdout.decode() if stdout else "",
                stderr=stderr.decode() if stderr else "",
                code=process.returncode
            )
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return CommandResult("", str(e), 1)

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from response with minimal processing"""
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

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        """Main loop with minimal output"""
        self.current_conversation_id = str(datetime.now().strftime("%Y%m%d_%H%M%S"))
        messages = [{"role": "user", "content": initial_prompt}]
        
        try:
            while True:
                self._print("Thinking...", "debug")
                response = await self.llm.get_response("", system_prompt, messages)
                
                if not response:
                    self._print("Failed to get response", "error")
                    break

                # Only print Claude's responses
                print(f"\n=== CLAUDE ===\n{response}\n============")
                
                messages.append({"role": "assistant", "content": response})
                
                # Execute commands silently
                commands = self.extract_commands(response)
                for cmd in commands:
                    result = await self.execute_command(cmd)
                    if result.output:
                        messages.append({"role": "user", "content": result.output})

                # Check completion
                if any(phrase in response.lower() for phrase in [
                    "task complete", "finished", "all done",
                    "completed successfully"
                ]):
                    break

        except KeyboardInterrupt:
            self._print("Shutting down...", "warning")
        except Exception as e:
            self._print(f"Error: {e}", "error")
            raise

    async def run(self, initial_prompt: str, system_prompt: str = "") -> None:
        """Run agent with controlled output"""
        try:
            self._print("Starting agent...", "info")
            await self.think_and_act(initial_prompt, system_prompt)
        except Exception as e:
            self._print(f"Run failed: {e}", "error")
            raise
