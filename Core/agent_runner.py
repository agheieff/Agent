from typing import List, Dict, Optional
from dataclasses import dataclass
from Clients.base import Message
from Tools.base import Tool

@dataclass
class AgentMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str

class AgentRunner:
    def __init__(self, provider: str, model: str = None):
        self.client = self._get_client(provider)
        self.model = model or self.client.config.default_model
        self.conversation: List[AgentMessage] = []
        self.tools: Dict[str, Tool] = self._load_tools()

    def _get_client(self, provider: str):
        """Dynamically import and initialize the appropriate client"""
        provider_map = {
            'openai': 'OpenAIClient',
            'anthropic': 'AnthropicClient',
            'gemini': 'GeminiClient',
            'deepseek': 'DeepSeekClient'
        }
        
        try:
            module = __import__(f'Clients.API.{provider}', fromlist=[provider_map[provider]])
            client_class = getattr(module, provider_map[provider])
            return client_class()
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Unsupported provider: {provider}") from e

    def _load_tools(self) -> Dict[str, Tool]:
        """Discover and initialize available tools"""
        # Simplified tool discovery - would need implementation
        return {}  

    def run(self, prompt: str):
        """Main execution loop"""
        self.add_message('user', prompt)
        
        while True:
            response = self.client.chat_completion(
                messages=self._format_conversation(),
                model=self.model
            )
            
            self.add_message('assistant', response)
            
            if self._should_terminate(response):
                break

    def add_message(self, role: str, content: str):
        self.conversation.append(AgentMessage(role, content))

    def _format_conversation(self) -> List[Message]:
        return [
            Message(role=msg.role, content=msg.content)
            for msg in self.conversation
        ]

    def _should_terminate(self, response: str) -> bool:
        """Check if conversation should end"""
        return any(end_word in response.lower() 
                  for end_word in ['goodbye', 'farewell', 'exit'])
