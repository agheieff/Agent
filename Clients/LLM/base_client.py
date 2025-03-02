from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Union, Tuple, Any
from datetime import datetime

class TokenUsage:
    """Class to track token usage and cost"""
    def __init__(self, prompt_tokens=0, completion_tokens=0, total_tokens=0, 
                 prompt_cost=0.0, completion_cost=0.0, total_cost=0.0,
                 model="", timestamp=None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.prompt_cost = prompt_cost
        self.completion_cost = completion_cost
        self.total_cost = total_cost
        self.model = model
        self.timestamp = timestamp or datetime.now()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert usage data to dictionary"""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_cost": self.prompt_cost,
            "completion_cost": self.completion_cost,
            "total_cost": self.total_cost,
            "model": self.model,
            "timestamp": self.timestamp.isoformat()
        }
        
    def __str__(self) -> str:
        """Human-readable representation"""
        return (f"Model: {self.model}\n"
                f"Tokens: {self.prompt_tokens} in + {self.completion_tokens} out = {self.total_tokens} total\n"
                f"Cost: ${self.total_cost:.6f} (${self.prompt_cost:.6f} in + ${self.completion_cost:.6f} out)")

class BaseLLMClient(ABC):
    """Abstract base class for LLM clients with token tracking"""
    
    def __init__(self):
        # Track usage history
        self.usage_history = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        
    def add_usage(self, usage: TokenUsage):
        """Add usage data to history and update totals"""
        self.usage_history.append(usage)
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.total_cost += usage.total_cost
        
        # Print usage information to stdout
        print(f"\n[API USAGE] {usage}")
        print(f"[API USAGE] Total cost so far: ${self.total_cost:.6f} ({self.total_tokens} tokens)")
        
    def get_usage_summary(self) -> Dict[str, Any]:
        """Get summary of all API usage"""
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "calls": len(self.usage_history),
            "history": [usage.to_dict() for usage in self.usage_history]
        }
    
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
        
    @abstractmethod
    def calculate_token_cost(self, usage: Dict[str, int], model: str) -> Dict[str, float]:
        """
        Calculate the cost based on token usage and model
        
        Args:
            usage: Dictionary with 'prompt_tokens' and 'completion_tokens' 
            model: Model name used for the request
            
        Returns:
            Dictionary with 'prompt_cost', 'completion_cost', and 'total_cost'
        """
        pass