
from dataclasses import dataclass
from typing import List, Dict
from Clients import BaseClient, Message
import asyncio
from Core.utils import get_multiline_input  # <-- Added import here

@dataclass
class AgentMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str

class AgentRunner:
    def __init__(self, provider: str, model: str = None):
        self.client = self._init_client(provider)
        self.model = model or self.client.config.default_model
        self.messages: List[AgentMessage] = []

    def _init_client(self, provider: str) -> BaseClient:
        """Initialize the appropriate client based on provider name"""
        try:
            # Import the provider module dynamically
            module = __import__(f'Clients.API.{provider.lower()}', fromlist=['*'])
            
            # Look for classes that end with 'Client'
            for name, obj in module.__dict__.items():
                if name.endswith('Client') and name.lower().startswith(provider.lower()):
                    return obj()
            
            # If no match found by naming convention, look for any client class
            for name, obj in module.__dict__.items():
                if name.endswith('Client'):
                    return obj()
                    
            raise ValueError(f"No client class found in module Clients.API.{provider}")
        except ImportError as e:
            raise ImportError(f"Provider module not found: {provider}") from e
        except Exception as e:
            raise RuntimeError(f"Error initializing client for {provider}: {str(e)}") from e

    def add_message(self, role: str, content: str):
        self.messages.append(AgentMessage(role, content))

    async def _run_chat_cycle(self, prompt: str):
        self.add_message('user', prompt)
        
        client_messages = [
            Message(role=msg.role, content=msg.content)
            for msg in self.messages
        ]
        
        response = await self.client.chat_completion(
            messages=client_messages,
            model=self.model
        )
        
        self.add_message('assistant', response)
        return response

    def run(self, prompt: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            initial_response = loop.run_until_complete(self._run_chat_cycle(prompt))
            print(f"\nAssistant: {initial_response}")
            
            # Get follow-up prompts from the user
            while True:
                try:
                    follow_up = get_multiline_input("\nYou: ")
                    if not follow_up.strip():
                        continue
                        
                    response = loop.run_until_complete(self._run_chat_cycle(follow_up))
                    print(f"\nAssistant: {response}")
                    
                    if any(end_word in response.lower() 
                           for end_word in ['goodbye', 'farewell', 'exit']):
                        break
                except EOFError:
                    break
        except KeyboardInterrupt:
            print("\nSession ended by user")
        finally:
            loop.close()
