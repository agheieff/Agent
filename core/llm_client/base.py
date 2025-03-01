from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Union, Tuple

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    @abstractmethod
    async def get_response(
        self,
        prompt: str,
        system: str,
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False
    ) -> Optional[str]:
        """Get response from the model"""
        pass
        
    @abstractmethod
    async def check_for_user_input_request(
        self, 
        response: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Checks if the model is requesting user input.
        
        Args:
            response: The model's response text
            
        Returns:
            Tuple of (should_pause, question_for_user)
            - should_pause: True if user input is requested
            - question_for_user: The question to display to the user (if any)
        """
        pass
