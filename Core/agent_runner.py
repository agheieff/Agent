from dataclasses import dataclass
from typing import List, Dict, Optional
from Clients import BaseClient, Message
from Tools.base import Tool

@dataclass
class AgentMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str

class AgentRunner:
    def __init__(self, provider: str, model: str = None):
        self.client = self._init_client(provider)
        self.model = model or self.client.config.default_model
        self.messages: List[AgentMessage] = []
        self.tools: Dict[str, Tool] = {}

    def _init_client(self, provider: str) -> BaseClient:
        """Initialize the appropriate client based on provider name"""
        provider_map = {
            'openai': 'OpenAIClient',
            'anthropic': 'AnthropicClient',
            'gemini': 'GeminiClient',
            'deepseek': 'DeepSeekClient'
        }
        
        try:
            module = __import__(f'Clients.API.{provider}', fromlist=[provider_map[provider]])
            return getattr(module, provider_map[provider])()
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Unsupported provider: {provider}") from e

    def add_message(self, role: str, content: str):
        self.messages.append(AgentMessage(role, content))

    def run(self, prompt: str):
        """Main execution loop"""
        self.add_message('user', prompt)
        
        while True:
            # Format messages for the client
            client_messages = [
                Message(role=msg.role, content=msg.content)
                for msg in self.messages
            ]
            
            response = self.client.chat_completion(
                messages=client_messages,
                model=self.model
            )
            
            self.add_message('assistant', response)
            
            if self._should_end(response):
                break

    def _should_end(self, response: str) -> bool:
        """Check if conversation should terminate"""
        return any(end_word in response.lower() 
                 for end_word in ['goodbye', 'farewell', 'exit'])
