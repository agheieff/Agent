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

# Set up logging
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
        """Initialize the autonomous agent with required components."""
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
        """Initialize agent with core capabilities."""
        self.scheduler.start()
        self.setup_persistent_storage()
        self.setup_task_scheduling()
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

    def setup_task_scheduling(self):
        """Initialize task scheduler with maintenance tasks."""
        self.scheduler.add_job(
            self.cleanup_old_conversations,
            'interval',
            hours=24
        )
        self.logger.info("Scheduled tasks initialized.")

    def cleanup_old_conversations(self):
        """Clean up old conversation files to manage storage."""
        try:
            cutoff_days = 7  # Keep conversations for 7 days
            cutoff = datetime.now().timestamp() - (cutoff_days * 24 * 60 * 60)
            
            conv_dir = Path('memory/conversations')
            for file in conv_dir.glob('*.json'):
                if file.stat().st_mtime < cutoff:
                    file.unlink()
                    self.logger.info(f"Cleaned up old conversation: {file.name}")
        except Exception as e:
            self.logger.error(f"Error cleaning up conversations: {e}")

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results."""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            self.logger.info(f"Command executed successfully. Exit code: {result[2]}")
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return "", str(e), 1

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from code blocks in the response."""
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_block = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('```'):
                if in_code_block:
                    # End of code block
                    block_text = '\n'.join(current_block).strip()
                    if block_text:
                        commands.extend([cmd.strip() for cmd in block_text.split('\n') if cmd.strip()])
                    current_block = []
                    in_code_block = False
                else:
                    # Start of code block
                    in_code_block = True
                continue
            elif in_code_block and stripped:
                current_block.append(stripped)

        # Handle any unclosed code block
        if in_code_block and current_block:
            block_text = '\n'.join(current_block).strip()
            if block_text:
                commands.extend([cmd.strip() for cmd in block_text.split('\n') if cmd.strip()])

        self.logger.debug(f"Extracted commands: {commands}")
        return [cmd for cmd in commands if cmd]

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        """Main loop for autonomous thinking and action."""
        # Start a new conversation
        self.current_conversation_id = self.memory.create_conversation()
        
        # Initialize conversation with the initial prompt
        history = [{"role": "user", "content": initial_prompt}]
        self.memory.save_conversation(self.current_conversation_id, history)
        self.logger.info("Started new conversation with initial prompt")

        try:
            while True:
                # Get Claude's response based on full history
                self.logger.info("Requesting response from LLM...")
                response = await self.llm.get_response("", system_prompt, history)
                
                if not response:
                    self.logger.error("Failed to get LLM response")
                    break

                # Save Claude's response
                history.append({"role": "assistant", "content": response})
                self.memory.save_conversation(self.current_conversation_id, history)
                self.logger.info("Received and saved LLM response")

                # Extract commands from response
                commands = self.extract_commands(response)
                self.logger.info(f"Extracted {len(commands)} commands from response")

                # Execute all commands and add results to history
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
                        self.logger.info("Command output added to conversation history")

                # If no commands were found, check if we should continue
                if not commands:
                    self.logger.info("No commands in response - checking for conversation end")
                    # Look for clear end signals in the response
                    if any(phrase in response.lower() for phrase in [
                        "task complete",
                        "finished",
                        "all done",
                        "completed successfully"
                    ]):
                        self.logger.info("Detected task completion signal - ending conversation")
                        break

        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt - shutting down")
        except Exception as e:
            self.logger.error(f"Error in think_and_act loop: {e}")
            raise
        finally:
            self.scheduler.shutdown()

    async def run(self, initial_prompt: str, system_prompt: str = "") -> None:
        """Run the agent with the given initial prompt."""
        try:
            await self.think_and_act(initial_prompt, system_prompt)
        except Exception as e:
            self.logger.error(f"Error running agent: {e}")
            raise
