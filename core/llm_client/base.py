from abc import ABC, abstractmethod
from typing import Optional, List, Dict

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    async def get_response(
        self,
        prompt: str,
        system: str,
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096
    ) -> Optional[str]:
        """Get response from the model"""
        pass
