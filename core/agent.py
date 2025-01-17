# core/agent.py
from core.llm_client import AnthropicClient
from core.memory_manager import MemoryManager
import asyncio
import logging
from datetime import datetime
import uuid
from typing import Optional, Dict, List

class AutonomousAgent:
    def __init__(self, api_key: Optional[str] = None, system_user: str = 'aiagent'):
        self.llm = AnthropicClient(api_key)
        self.memory = MemoryManager()
        self.system = SystemControl(user=system_user)
        self.current_conversation_id = None

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results"""
        return await self.system.execute_command(command)

    async def think_and_act(self, prompt: str, system: str) -> str:
        """Process a thought and execute any necessary actions"""
        response = await self.think(prompt, system)
        
        # Parse response for commands (you'll need to implement command extraction)
        commands = self.extract_commands(response)
        
        results = []
        for cmd in commands:
            stdout, stderr, code = await self.execute(cmd)
            results.append({
                'command': cmd,
                'stdout': stdout,
                'stderr': stderr,
                'code': code
            })
            
        # Update the conversation with results
        if results:
            result_prompt = f"Command execution results:\n{str(results)}"
            await self.think(result_prompt, system)
            
        return response

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from the response"""
        # Simple implementation - you'll want to make this more robust
        commands = []
        if '```bash' in response:
            blocks = response.split('```bash')
            for block in blocks[1:]:
                cmd_block = block.split('```')[0].strip()
                commands.extend([cmd.strip() for cmd in cmd_block.split('\n') if cmd.strip()])
        return commands
