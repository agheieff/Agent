# core/agent.py
import asyncio
import logging
from datetime import datetime
import uuid
from typing import Optional, Dict, List, Tuple
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
    def __init__(self, api_key: Optional[str] = None, system_user: str = 'aiagent'):
        self.llm = AnthropicClient(api_key)
        self.memory = MemoryManager()
        self.system = SystemControl(user=system_user)
        self.current_conversation_id = None
        self.logger = logger

    def start_conversation(self) -> str:
        """Start a new conversation and return its ID"""
        self.current_conversation_id = self.memory.create_conversation()
        return self.current_conversation_id

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results"""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            self.logger.info(f"Command result: {result[2]}")
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return "", str(e), 1

    async def think_and_act(self, prompt: str, system: str) -> str:
        """Process a thought and execute any necessary actions"""
        if not self.current_conversation_id:
            self.start_conversation()

        # Load conversation history
        history = self.memory.load_conversation(self.current_conversation_id)
        
        # Get LLM response
        self.logger.info("Getting LLM response")
        response = await self.llm.get_response(prompt, system, history)
        
        if not response:
            self.logger.error("Failed to get LLM response")
            return "Failed to process request"

        # Save the user prompt and AI response to conversation history
        history.extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response}
        ])
        self.memory.save_conversation(self.current_conversation_id, history)

        # Extract and execute commands
        commands = self.extract_commands(response)
        if commands:
            results = []
            for cmd in commands:
                stdout, stderr, code = await self.execute(cmd)
                result = {
                    'command': cmd,
                    'stdout': stdout,
                    'stderr': stderr,
                    'code': code,
                    'timestamp': datetime.now().isoformat()
                }
                results.append(result)
                
                # Save command results to conversation
                history.append({
                    "role": "system",
                    "content": f"Command execution result:\n{str(result)}"
                })
            
            self.memory.save_conversation(self.current_conversation_id, history)
            
            # Get LLM's analysis of the results
            result_prompt = f"Command execution results:\n{str(results)}\n\nPlease analyze these results and determine next steps."
            analysis = await self.llm.get_response(result_prompt, system, history)
            
            if analysis:
                history.append({
                    "role": "assistant",
                    "content": analysis
                })
                self.memory.save_conversation(self.current_conversation_id, history)
                response += f"\n\nAnalysis of results:\n{analysis}"
            
        return response

    def extract_commands(self, response: str) -> List[str]:
        """
        Extract commands from the response.
        Handles multiple commands and different code block types.
        """
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_block = []
        current_language = None
        
        for line in lines:
            stripped = line.strip()
            
            # Check for code block start
            if stripped.startswith('```'):
                if in_code_block:
                    # End of code block
                    if current_language in ['bash', 'shell', 'sh', None]:
                        # Process the commands in the block
                        block_text = '\n'.join(current_block).strip()
                        if block_text:
                            # Split multi-line commands and add them individually
                            block_commands = [cmd.strip() for cmd in block_text.split('\n') if cmd.strip()]
                            commands.extend(block_commands)
                    current_block = []
                    in_code_block = False
                    current_language = None
                else:
                    # Start of code block
                    in_code_block = True
                    # Extract language if specified
                    if len(stripped) > 3:
                        current_language = stripped[3:].strip().lower()
                    
            elif in_code_block:
                current_block.append(line)
                
        self.logger.info(f"Extracted {len(commands)} commands: {commands}")
        return commands

    async def analyze_conversation(self, conversation_id: Optional[str] = None) -> str:
        """Analyze the conversation history and provide insights"""
        conv_id = conversation_id or self.current_conversation_id
        if not conv_id:
            return "No conversation to analyze"
            
        history = self.memory.load_conversation(conv_id)
        if not history:
            return "Conversation history is empty"
            
        analysis_prompt = """Please analyze this conversation history and provide insights on:
        1. Key decisions and actions taken
        2. Success rate of executed commands
        3. Overall progress toward goals
        4. Potential areas for improvement
        """
        
        analysis = await self.llm.get_response(analysis_prompt, "", history)
        return analysis
