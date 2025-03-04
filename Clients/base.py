from abc import ABC, abstractmethod
import logging
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ModelInfo:
    def __init__(self,
                 name: str,
                 api_name: str,
                 supports_reasoning: bool = True,
                 prefers_separate_system_prompt: bool = True,
                 context_window: int = 128000,
                 input_price: float = 0.0,
                 output_price: float = 0.0,
                 input_cache_read_price: Optional[float] = None,
                 input_cache_write_price: Optional[float] = None,
                 discount_hours: Optional[Tuple[int, int, int, int]] = None,
                 discount_rate: float = 0.0):
        self.name = name
        self.api_name = api_name
        self.supports_reasoning = supports_reasoning
        self.prefers_separate_system_prompt = prefers_separate_system_prompt
        self.context_window = context_window
        self.input_price = input_price
        self.output_price = output_price
        self.input_cache_read_price = input_cache_read_price or input_price * 0.1
        self.input_cache_write_price = input_cache_write_price or input_price * 1.25
        self.discount_hours = discount_hours
        self.discount_rate = discount_rate

    def get_pricing(self) -> Dict[str, float]:
        pricing = {
            "input": self.input_price / 1_000_000,
            "output": self.output_price / 1_000_000
        }
        if self.input_cache_read_price is not None:
            pricing["input_cache_read"] = self.input_cache_read_price / 1_000_000
        if self.input_cache_write_price is not None:
            pricing["input_cache_write"] = self.input_cache_write_price / 1_000_000

        if self.discount_hours and self.discount_rate > 0:
            now = datetime.now()
            current_mins = now.hour * 60 + now.minute
            start_hour, start_minute, end_hour, end_minute = self.discount_hours
            start_mins = start_hour * 60 + start_minute
            end_mins = end_hour * 60 + end_minute

            discount_applied = False
            if end_mins < start_mins:
                if current_mins >= start_mins or current_mins <= end_mins:
                    discount_applied = True
            else:
                if start_mins <= current_mins <= end_mins:
                    discount_applied = True

            if discount_applied:
                multiplier = 1.0 - self.discount_rate
                for key in pricing:
                    pricing[key] *= multiplier

        return pricing

class TokenUsage:
    def __init__(self, prompt_tokens=0, completion_tokens=0, total_tokens=0, model="", timestamp=None):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.model = model
        self.timestamp = timestamp or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "model": self.model,
            "timestamp": self.timestamp.isoformat()
        }

class BaseLLMClient(ABC):
    def __init__(self, api_key: str = ""):
        if api_key and api_key.startswith("sk-") and len(api_key) < 20:
            logger.warning("API key has unexpected format or length")

        self.usage_history: List[TokenUsage] = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.models: Dict[str, ModelInfo] = {}
        self.default_model = None

        self._initialize_client(api_key)
        self._register_models()

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        if model_name in self.models:
            return self.models[model_name]
        for model in self.models.values():
            if model.api_name == model_name:
                return model
        return None

    def get_available_models(self) -> List[str]:
        return list(self.models.keys())

    def add_usage(self, usage: TokenUsage):
        self.usage_history.append(usage)
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_tokens += usage.total_tokens

    def get_usage_summary(self) -> Dict[str, Any]:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": len(self.usage_history),
            "history": [usage.to_dict() for usage in self.usage_history]
        }

    def extract_usage_data(self, message, model_name: str) -> Dict[str, int]:
        usage_data = None
        try:
            if hasattr(message, "usage"):
                if hasattr(message.usage, "input_tokens") and hasattr(message.usage, "output_tokens"):
                    usage_data = {
                        "prompt_tokens": message.usage.input_tokens,
                        "completion_tokens": message.usage.output_tokens,
                        "total_tokens": message.usage.input_tokens + message.usage.output_tokens
                    }
                elif hasattr(message.usage, "prompt_tokens") and hasattr(message.usage, "completion_tokens"):
                    usage_data = {
                        "prompt_tokens": message.usage.prompt_tokens,
                        "completion_tokens": message.usage.completion_tokens,
                        "total_tokens": message.usage.total_tokens
                    }
                elif isinstance(message.usage, dict):
                    usage_data = {
                        "prompt_tokens": message.usage.get("prompt_tokens", 0),
                        "completion_tokens": message.usage.get("completion_tokens", 0),
                        "total_tokens": message.usage.get("total_tokens", 0)
                    }
            if not usage_data:
                logger.warning("Token usage not available from API, using estimation")
                response_text = self.extract_response_content(message)
                estimated_prompt_tokens = 10
                if isinstance(message, list):
                    estimated_prompt_tokens = sum(len(m.get("content", "").split()) for m in message)
                estimated_completion_tokens = len(response_text.split())
                usage_data = {
                    "prompt_tokens": estimated_prompt_tokens,
                    "completion_tokens": estimated_completion_tokens,
                    "total_tokens": estimated_prompt_tokens + estimated_completion_tokens
                }
        except Exception as e:
            logger.warning(f"Error calculating token usage: {e}")
            usage_data = {
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20
            }
        return usage_data

    def extract_response_content(self, message) -> str:
        try:
            if hasattr(message, 'content'):
                if isinstance(message.content, list):
                    texts = []
                    for block in message.content:
                        if isinstance(block, dict) and block.get('type') == 'text' and 'text' in block:
                            texts.append(block['text'])
                        elif hasattr(block, 'text'):
                            texts.append(block.text)
                    if texts:
                        return "\n".join(texts)
                    if message.content:
                        first = message.content[0]
                        return first.text if hasattr(first, 'text') else first.get('text', "")
                elif isinstance(message.content, str):
                    return message.content
            elif hasattr(message, 'completion'):
                return message.completion
            elif hasattr(message, 'choices') and message.choices:
                first = message.choices[0]
                if hasattr(first, 'message') and hasattr(first.message, 'content'):
                    return first.message.content
            return str(message)
        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return f"Error parsing response: {e}"

    def track_usage(self, message, model_name: str):
        usage_data = self.extract_usage_data(message, model_name)
        token_usage = TokenUsage(
            prompt_tokens=usage_data["prompt_tokens"],
            completion_tokens=usage_data["completion_tokens"],
            total_tokens=usage_data["total_tokens"],
            model=model_name
        )
        self.add_usage(token_usage)

    async def generate_response(self, conversation_history: List[Dict]) -> str:
        try:
            model_info = self.get_model_info(self.default_model)
            if model_info and not model_info.prefers_separate_system_prompt:
                combined = "\n".join(msg.get("content", "") for msg in conversation_history)
                if not combined.strip():
                    combined = "Hello, please respond."
                conversation_history = [{"role": "user", "content": combined.strip()}]

            response = await self.get_response(
                prompt=None,
                system=None,
                conversation_history=conversation_history,
                temperature=0.5,
                max_tokens=model_info.context_window if model_info else 4096,
                tool_usage=False,
                model=self.default_model
            )
            if response is None:
                return "I encountered an error generating a response. Please try again."
            return response
        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            return f"I encountered an error generating a response: {e}"

    async def get_response(
        self,
        prompt: Optional[str],
        system: Optional[str],
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False,
        model: Optional[str] = None
    ) -> Optional[str]:
        try:
            model_name = model or self.default_model
            model_info = self.get_model_info(model_name)
            messages = conversation_history or []
            if not messages:
                if system and (not model_info or model_info.prefers_separate_system_prompt):
                    messages.append({"role": "system", "content": system})
                    if prompt:
                        messages.append({"role": "user", "content": prompt})
                else:
                    combined = (system + "\n\n" + prompt) if (system and prompt) else (system or prompt or "")
                    if combined:
                        messages.append({"role": "user", "content": combined})

            api_model_name = model_info.api_name if model_info else model_name

            response = await self._make_api_call(
                messages,
                api_model_name,
                temperature,
                max_tokens,
                tool_usage
            )

            self.track_usage(response, api_model_name)
            return self.extract_response_content(response)

        except Exception as e:
            logger.error(f"API call failed: {e}")
            return None

    async def _make_api_call(
        self,
        messages: List[Dict],
        model_name: str,
        temperature: float,
        max_tokens: int,
        tool_usage: bool
    ) -> Any:
        if not hasattr(self, 'client'):
            raise NotImplementedError("Subclass must initialize self.client")
        if hasattr(self.client, 'messages') and hasattr(self.client.messages, 'create'):
            params = {
                "model": model_name,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages
            }
            return self.client.messages.create(**params)
        elif hasattr(self.client, 'chat') and hasattr(self.client.chat, 'completions'):
            params = {
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            if tool_usage:
                params["functions"] = [{
                    "name": "tool",
                    "description": "Tool usage placeholder",
                    "parameters": {}
                }]
                params["function_call"] = "auto"
            return self.client.chat.completions.create(**params)
        else:
            raise NotImplementedError("Unknown API pattern for this client")

    @abstractmethod
    def _initialize_client(self, api_key: str) -> None:
        pass

    @abstractmethod
    def _register_models(self) -> None:
        pass

    def adjust_prompts(self, system_prompt: Optional[str], user_prompt: str) -> Tuple[Optional[str], str]:
        model_info = self.get_model_info(self.default_model)
        if model_info and not model_info.prefers_separate_system_prompt and system_prompt:
            combined = system_prompt + "\n\n" + user_prompt
            return None, combined
        return system_prompt, user_prompt
