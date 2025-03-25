from dataclasses import dataclass
from typing import List, Dict
from Clients import BaseClient, Message

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
        provider_map = {
            'anthropic': 'AnthropicClient',
            'deepseek': 'DeepSeekClient'
        }
        
        module = __import__(f'Clients.API.{provider}', fromlist=[provider_map[provider]])
        return getattr(module, provider_map[provider])()

    def add_message(self, role: str, content: str):
        self.messages.append(AgentMessage(role, content))

    def run(self, prompt: str):
        self.add_message('user', prompt)
        
        while True:
            client_messages = [
                Message(role=msg.role, content=msg.content)
                for msg in self.messages
            ]
            
            response = self.client.chat_completion(
                messages=client_messages,
                model=self.model
            )
            
            self.add_message('assistant', response)
            
            if any(end_word in response.lower() 
                  for end_word in ['goodbye', 'farewell', 'exit']):
                break
