# core/agent.py
import asyncio
import logging
import os
from typing import Optional, List, Tuple
from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.llm_client import AnthropicClient
from core.memory_manager import MemoryManager
from core.system_control import SystemControl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class AutonomousAgent:
    def __init__(self, api_key: Optional[str] = None, system_user: str = 'claude'):
        if not api_key:
            raise ValueError("Anthropic API key is required")
            
        self.llm = AnthropicClient(api_key)
        self.memory = MemoryManager()
        self.system = SystemControl(user=system_user)
        self.current_conversation_id = None
        self.logger = logger
        self.initialize_agent()

    def initialize_agent(self):
        """Initialize agent with basic setup."""
        self.setup_persistent_storage()
        self.logger.info("Agent initialized successfully.")

    def setup_persistent_storage(self):
        """Set up persistent storage directories."""
        storage_paths = [
            'memory/logs',
            'memory/conversations',
            'memory/tasks',
            'memory/docs',
            'memory/context'
        ]
        for path in storage_paths:
            os.makedirs(path, exist_ok=True)
        self.logger.info("Persistent storage directories created.")

    def extract_commands(self, response: str) -> List[str]:
        """
        Extract commands from response more reliably.
        - Handles both ``` and ```bash/sh code blocks
        - Properly handles multiline commands
        - Ignores commented lines
        """
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_command = []
        
        for line in lines:
            stripped = line.strip()
            
            # Handle code block markers
            if stripped.startswith('```'):
                if not in_code_block:
                    # Start of code block
                    in_code_block = True
                    language = stripped[3:].strip().lower()
                    # Only process shell/bash blocks or unmarked blocks
                    if language and language not in ['sh', 'shell', 'bash']:
                        in_code_block = False
                else:
                    # End of code block
                    if current_command:
                        commands.append(' '.join(current_command))
                        current_command = []
                    in_code_block = False
                continue
                
            if in_code_block:
                # Skip empty lines and comments
                if not stripped or stripped.startswith('#'):
                    continue
                    
                # Handle line continuation
                if stripped.endswith('\\'):
                    current_command.append(stripped[:-1].strip())
                else:
                    current_command.append(stripped)
                    commands.append(' '.join(current_command))
                    current_command = []

        # Handle any unclosed command
        if current_command:
            commands.append(' '.join(current_command))

        self.logger.debug(f"Extracted commands: {commands}")
        return [cmd for cmd in commands if cmd]

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results."""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            stdout, stderr, code = result
            
            if code == 0:
                self.logger.info(f"Command executed successfully")
            else:
                self.logger.warning(f"Command returned non-zero exit code: {code}")
                
            if stdout:
                self.logger.debug(f"Command stdout: {stdout[:200]}...")
            if stderr:
                self.logger.debug(f"Command stderr: {stderr[:200]}...")
                
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return "", str(e), 1

    def format_message_for_log(self, message: dict) -> str:
        """Format a single message for the conversation log."""
        role = message['role']
        content = message.get('content', '')
        return f"\n=== {role.upper()} ===\n{content}\n"

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        """Main autonomous loop with improved conversation flow and logging."""
        # Start new conversation
        self.current_conversation_id = self.memory.create_conversation()
        
        # Start with just the initial prompt
        messages = [{"role": "user", "content": initial_prompt}]
        self.memory.save_conversation(self.current_conversation_id, messages)
        self.logger.info(f"Starting conversation {self.current_conversation_id}")

        try:
            while True:
                # Get Claude's response based on current conversation
                self.logger.info("Requesting response from LLM...")
                response = await self.llm.get_response("", system_prompt, messages)
                
                if not response:
                    self.logger.error("Failed to get LLM response")
                    break

                # Add Claude's response to conversation and log only the new message
                messages.append({"role": "assistant", "content": response})
                self.memory.save_conversation(self.current_conversation_id, messages)
                print(self.format_message_for_log(messages[-1]))

                # Extract and execute commands
                commands = self.extract_commands(response)
                self.logger.info(f"Extracted {len(commands)} commands")

                for cmd in commands:
                    stdout, stderr, code = await self.execute(cmd)
                    output = stdout if stdout else stderr
                    if output:
                        # Add command output as user message and log only the new message
                        new_message = {"role": "user", "content": output}
                        messages.append(new_message)
                        self.memory.save_conversation(self.current_conversation_id, messages)
                        print(self.format_message_for_log(new_message))

                # Check for conversation completion
                if not commands and any(phrase in response.lower() for phrase in [
                    "task complete",
                    "finished",
                    "all done",
                    "completed successfully"
                ]):
                    self.logger.info("Task completion detected - ending conversation")
                    break

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt - shutting down")
        except Exception as e:
            self.logger.error(f"Error in think_and_act loop: {e}")
            raise

    async def run(self, initial_prompt: str, system_prompt: str = "") -> None:
        """Run the agent with the given prompts."""
        try:
            self.logger.info("Starting agent run...")
            await self.think_and_act(initial_prompt, system_prompt)
        except Exception as e:
            self.logger.error(f"Error running agent: {e}")
            raise
