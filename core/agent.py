# core/agent.py
from core.llm_client import AnthropicClient
from core.memory_manager import MemoryManager
import asyncio
import logging
from datetime import datetime
import uuid
from typing import Optional, Dict, List

class AutonomousAgent:
    def __init__(self, api_key: Optional[str] = None):
        self.llm = AnthropicClient(api_key)
        self.memory = MemoryManager()
        self.current_conversation_id = None
        
    def start_new_conversation(self):
        """Start a new conversation with a unique ID."""
        self.current_conversation_id = str(uuid.uuid4())
        return self.current_conversation_id
        
    async def think(self, prompt: str, system: str) -> str:
        """Process a thought with conversation history."""
        if not self.current_conversation_id:
            self.start_new_conversation()
            
        # Load conversation history
        history = self.memory.load_conversation(self.current_conversation_id)
        
        # Get response
        response = await self.llm.get_response(prompt, system, history)
        
        if response:
            # Create serializable message objects
            user_message = {
                "role": "user",
                "content": str(prompt)
            }
            assistant_message = {
                "role": "assistant",
                "content": str(response)
            }
            
            # Update conversation history
            if not history:
                history = []
            history.extend([user_message, assistant_message])
            
            # Save conversation
            self.memory.save_conversation(self.current_conversation_id, history)
            
        return response
