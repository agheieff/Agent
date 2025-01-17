# core/agent.py
import asyncio
import logging
from typing import Optional, List, Tuple
from pathlib import Path
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.llm_client import AnthropicClient
from core.memory_manager import MemoryManager
from core.system_control import SystemControl

logging.basicConfig(
    level=logging.DEBUG,
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
        ]
        for path in storage_paths:
            os.makedirs(path, exist_ok=True)
        self.logger.info("Persistent storage directories created.")

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from code blocks in the response."""
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_block = []
        current_language = None

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    # Get language if specified
                    lang_spec = stripped[3:].strip().lower()
                    current_language = lang_spec if lang_spec else None
                    continue
                else:
                    # End of code block
                    block_text = '\n'.join(current_block).strip()
                    if block_text and (not current_language or current_language in ['sh', 'shell', 'bash']):
                        commands.extend([cmd.strip() for cmd in block_text.split('\n') if cmd.strip()])
                    current_block = []
                    current_language = None
                    in_code_block = False
                continue
            
            if in_code_block:
                current_block.append(stripped)

        # Handle any unclosed code block
        if in_code_block and current_block:
            block_text = '\n'.join(current_block).strip()
            if block_text and (not current_language or current_language in ['sh', 'shell', 'bash']):
                commands.extend([cmd.strip() for cmd in block_text.split('\n') if cmd.strip()])

        self.logger.debug(f"Found commands: {commands}")
        return [cmd for cmd in commands if cmd and not cmd.startswith('```')]

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results."""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            self.logger.info(f"Command executed successfully. Exit code: {result[2]}")
            self.logger.debug(f"Command stdout: {result[0]}")
            self.logger.debug(f"Command stderr: {result[1]}")
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return "", str(e), 1

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        """Main autonomous loop with correct conversation flow."""
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

                # Add Claude's response to conversation
                messages.append({"role": "assistant", "content": response})
                self.memory.save_conversation(self.current_conversation_id, messages)
                self.logger.debug(f"Assistant response: {response}")

                # Extract any commands
                commands = self.extract_commands(response)
                self.logger.info(f"Extracted {len(commands)} commands: {commands}")

                if commands:
                    # Execute each command
                    for cmd in commands:
                        stdout, stderr, code = await self.execute(cmd)
                        output = stdout if stdout else stderr
                        if output:
                            # Add command output as user message
                            messages.append({"role": "user", "content": output})
                            self.logger.debug(f"Added command output: {output}")
                            self.memory.save_conversation(self.current_conversation_id, messages)
                else:
                    self.logger.info("No commands found in response")
                    if any(phrase in response.lower() for phrase in [
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
