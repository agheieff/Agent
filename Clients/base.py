from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Union, Tuple, Any
from datetime import datetime

class TokenUsage:
    def __init__(self, prompt_tokens=0, completion_tokens=0, total_tokens=0, 
                 prompt_cost=0.0, completion_cost=0.0, total_cost=0.0,
                 model="", timestamp=None, cache_hit=False):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.prompt_cost = prompt_cost
        self.completion_cost = completion_cost
        self.total_cost = total_cost
        self.model = model
        self.timestamp = timestamp or datetime.now()
        self.cache_hit = cache_hit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "prompt_cost": self.prompt_cost,
            "completion_cost": self.completion_cost,
            "total_cost": self.total_cost,
            "model": self.model,
            "timestamp": self.timestamp.isoformat(),
            "cache_hit": self.cache_hit
        }

    def __str__(self) -> str:
        cache_status = " (cache hit)" if self.cache_hit else ""
        return (f"Model: {self.model}{cache_status}\n"
                f"Tokens: {self.prompt_tokens} in + {self.completion_tokens} out = {self.total_tokens} total\n"
                f"Cost: ${self.total_cost:.6f} (${self.prompt_cost:.6f} in + ${self.completion_cost:.6f} out)")

class BaseLLMClient(ABC):
    def __init__(self):
        self.usage_history = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0

    def add_usage(self, usage: TokenUsage):
        self.usage_history.append(usage)
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens
        self.total_cost += usage.total_cost

        print(f"\n[API USAGE] {usage}")
        print(f"[API USAGE] Total cost so far: ${self.total_cost:.6f} ({self.total_tokens} tokens)")

    def get_usage_summary(self) -> Dict[str, Any]:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "calls": len(self.usage_history),
            "history": [usage.to_dict() for usage in self.usage_history]
        }

    def calculate_token_cost(self, usage: Dict[str, int], model_pricing: Dict[str, float], 
                             cache_hit: bool = False, cache_write: bool = False) -> Dict[str, float]:
        if cache_hit and "input_cache_read" in model_pricing:
            prompt_cost = usage["prompt_tokens"] * model_pricing["input_cache_read"]
        elif cache_write and "input_cache_write" in model_pricing:
            prompt_cost = usage["prompt_tokens"] * model_pricing["input_cache_write"]
        else:
            prompt_cost = usage["prompt_tokens"] * model_pricing["input"]

        completion_cost = usage["completion_tokens"] * model_pricing["output"]
        total_cost = prompt_cost + completion_cost

        return {
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "total_cost": total_cost,
            "cache_hit": cache_hit,
            "cache_write": cache_write
        }

    @abstractmethod
    async def get_response(
        self,
        prompt: str,
        system: str,
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False,
        model: Optional[str] = None
    ) -> Optional[str]:
        pass

    @abstractmethod
    async def check_for_user_input_request(
        self, 
        response: str
    ) -> Tuple[bool, Optional[str]]:
        pass

    @abstractmethod
    async def generate_response(
        self, 
        conversation_history: List[Dict]
    ) -> str:
        pass

    @abstractmethod
    def get_model_pricing(self, model: str) -> Dict[str, float]:
        pass
