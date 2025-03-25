from typing import List, Dict
from dataclasses import dataclass
from .model_interface import ModelInterface
from Tools.base import Tool

@dataclass
class AgentMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str

class AgentRunner:
    def __init__(self, provider: str, model: str = None):
        self.model = ModelInterface(provider)
        self.tools = self._load_tools()
        self.conversation = []
        
    def _load_tools(self) -> Dict[str, Tool]:
        """Discover and initialize all available tools"""
        return {}  # Implementation omitted
        
    def run(self, prompt: str):
        self.add_message('user', prompt)
        while True:
            response = self.model.generate(self.conversation)
            self.add_message('assistant', response)
            
            if self._should_terminate(response):
                break
                
    def add_message(self, role: str, content: str):
        self.conversation.append(AgentMessage(role, content))
