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

# Set up logging with more verbose output
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more detailed logging
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
        self.scheduler = AsyncIOScheduler()
        self.initialize_agent()

    def initialize_agent(self):
        self.scheduler.start()
        self.setup_persistent_storage()
        self.setup_task_scheduling()
        self.logger.info("Agent initialized successfully.")

    def setup_persistent_storage(self):
        storage_paths = [
            'memory/logs',
            'memory/conversations',
        ]
        for path in storage_paths:
            os.makedirs(path, exist_ok=True)
        self.logger.info("Persistent storage directories created.")

    def setup_task_scheduling(self):
        self.scheduler.add_job(
            self.cleanup_old_conversations,
            'interval',
            hours=24
        )

    def cleanup_old_conversations(self):
        try:
            cutoff_days = 7
            cutoff = datetime.now().timestamp() - (cutoff_days * 24 * 60 * 60)
            
            conv_dir = Path('memory/conversations')
            for file in conv_dir.glob('*.json'):
                if file.stat().st_mtime < cutoff:
                    file.unlink()
                    self.logger.info(f"Cleaned up old conversation: {file.name}")
        except Exception as e:
            self.logger.error(f"Error cleaning up conversations: {e}")

    async def execute(self, command: str) -> Tuple[str, str, int]:
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

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from code blocks in the response with improved parsing."""
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_block = []
        current_language = None

        for line in lines:
            stripped = line.strip()

            # Check for code block start with optional language
            if stripped.startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    # Check if language is specified
                    lang_spec = stripped[3:].strip().lower()
                    current_language = lang_spec if lang_spec else None
                    continue
                else:
                    # End of code block
                    block_text = '\n'.join(current_block).strip()
                    if block_text:
                        # Only add commands from shell/bash blocks or unspecified blocks
                        if not current_language or current_language in ['sh', 'shell', 'bash']:
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

        # Log found commands for debugging
        self.logger.debug(f"Found commands: {commands}")
        return [cmd for cmd in commands if cmd and not cmd.startswith('```')]

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        """Main autonomous loop with improved conversation management."""
        # Start new conversation
        self.current_conversation_id = self.memory.create_conversation()
        
        # Initialize conversation with both system prompt and initial prompt
        history = []
        
        # Add initial prompt to history
        history.append({"role": "user", "content": initial_prompt})
        self.logger.info(f"Starting conversation {self.current_conversation_id} with initial prompt: {initial_prompt}")
        
        # Save initial state
        self.memory.save_conversation(self.current_conversation_id, history)

        try:
            while True:
                # Get Claude's response
                self.logger.info("Requesting response from LLM...")
                response = await self.llm.get_response(
                    prompt="",  # Empty because we're using conversation history
                    system=system_prompt,
                    conversation_history=history
                )
                
                if not response:
                    self.logger.error("Failed to get LLM response")
                    break

                # Log full response for debugging
                self.logger.debug(f"Full LLM response: {response}")

                # Save Claude's response
                history.append({"role": "assistant", "content": response})
                self.memory.save_conversation(self.current_conversation_id, history)

                # Extract and execute commands
                commands = self.extract_commands(response)
                self.logger.info(f"Extracted {len(commands)} commands: {commands}")

                if commands:
                    for cmd in commands:
                        stdout, stderr, code = await self.execute(cmd)
                        
                        # Add command output to history
                        output = stdout if stdout else stderr
                        if output:
                            history.append({
                                "role": "system",
                                "content": f"Command output:\n{output}"
                            })
                            self.memory.save_conversation(self.current_conversation_id, history)
                else:
                    self.logger.info("No commands found in response")
                    # Check for conversation end signals
                    if any(phrase in response.lower() for phrase in [
                        "task complete",
                        "finished",
                        "all done",
                        "completed successfully"
                    ]):
                        self.logger.info("Task completion detected - ending conversation")
                        break

                # Save after each iteration
                self.memory.save_conversation(self.current_conversation_id, history)

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt - shutting down")
        except Exception as e:
            self.logger.error(f"Error in think_and_act loop: {e}")
            raise
        finally:
            self.scheduler.shutdown()

    async def run(self, initial_prompt: str, system_prompt: str = "") -> None:
        """Run the agent with the given prompts."""
        try:
            self.logger.info("Starting agent run...")
            await self.think_and_act(initial_prompt, system_prompt)
        except Exception as e:
            self.logger.error(f"Error running agent: {e}")
            raise
