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
            current_time = datetime.now()
            current_hour = current_time.hour
            current_minute = current_time.minute

            start_hour, start_minute, end_hour, end_minute = self.discount_hours
            current_time_mins = current_hour * 60 + current_minute
            start_time_mins = start_hour * 60 + start_minute
            end_time_mins = end_hour * 60 + end_minute

            discount_applied = False
            if end_time_mins < start_time_mins:
                if current_time_mins >= start_time_mins or current_time_mins <= end_time_mins:
                    discount_applied = True
            else:
                if start_time_mins <= current_time_mins <= end_time_mins:
                    discount_applied = True

            if discount_applied:
                discount_multiplier = 1.0 - self.discount_rate
                for key in pricing:
                    pricing[key] = pricing[key] * discount_multiplier

        return pricing

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
    def __init__(self, api_key: str = ""):
        if api_key and api_key.startswith("sk-") and len(api_key) < 20:
            logger.warning("API key has unexpected format or length")

        self.usage_history = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models: Dict[str, ModelInfo] = {}
        self.default_model = None
        self.max_model_tokens = 128000


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
        self.total_cost += usage.total_cost

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

    def extract_usage_data(self, message, model_name: str) -> Tuple[Dict[str, int], bool, bool]:

        usage_data = None
        cache_hit = False
        cache_write = False

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


                if hasattr(message, "cache") and message.cache:
                    if hasattr(message.cache, "status"):
                        if message.cache.status == "hit":
                            cache_hit = True
                        elif message.cache.status == "write":
                            cache_write = True
                elif hasattr(message, "cached") and message.cached:
                    cache_hit = True

            if not usage_data:
                logger.warning("Token usage not available from API, using estimation")

                response_text = self.extract_response_content(message)

                if isinstance(message, list):
                    estimated_prompt_tokens = sum([len(m.get("content", "").split()) * 1.3 for m in message])
                else:

                    estimated_prompt_tokens = 10

                estimated_completion_tokens = len(response_text.split()) * 1.3

                usage_data = {
                    "prompt_tokens": int(estimated_prompt_tokens),
                    "completion_tokens": int(estimated_completion_tokens),
                    "total_tokens": int(estimated_prompt_tokens + estimated_completion_tokens)
                }
        except Exception as e:
            logger.warning(f"Error calculating token usage: {e}")
            usage_data = {
                "prompt_tokens": 10,
                "completion_tokens": 10,
                "total_tokens": 20
            }

        return usage_data, cache_hit, cache_write

    def extract_response_content(self, message) -> str:

        try:

            if hasattr(message, 'content') and isinstance(message.content, list):

                text_blocks = []

                for content_block in message.content:

                    if isinstance(content_block, dict):

                        if content_block.get('type') == 'text' and 'text' in content_block:
                            text_blocks.append(content_block['text'])

                    elif hasattr(content_block, 'type'):
                        if content_block.type == 'text' and hasattr(content_block, 'text'):
                            text_blocks.append(content_block.text)

                if text_blocks:
                    return '\n'.join(text_blocks)


                if len(message.content) > 0:
                    if hasattr(message.content[0], 'text'):
                        return message.content[0].text
                    elif isinstance(message.content[0], dict) and 'text' in message.content[0]:
                        return message.content[0]['text']


            elif hasattr(message, 'content') and isinstance(message.content, str):
                return message.content


            elif hasattr(message, 'completion'):
                return message.completion


            elif hasattr(message, 'choices') and message.choices and len(message.choices) > 0:
                if hasattr(message.choices[0], 'message') and hasattr(message.choices[0].message, 'content'):
                    return message.choices[0].message.content


            return str(message)

        except Exception as e:
            logger.error(f"Error extracting response content: {e}")
            return f"Error parsing response: {e}"

    def track_usage(self, usage_data: Dict[str, int], model_name: str, cache_hit: bool = False, cache_write: bool = False):
        import asyncio
        from Output.output_manager import output_manager

        model_info = self.get_model_info(model_name)
        if model_info:
            model_pricing = model_info.get_pricing()
        else:
            logger.warning(f"No model info found for {model_name}, using default pricing")
            model_pricing = {"input": 0.0, "output": 0.0}

        costs = self.calculate_token_cost(
            usage_data,
            model_pricing,
            cache_hit=cache_hit,
            cache_write=cache_write
        )

        token_usage = TokenUsage(
            prompt_tokens=usage_data["prompt_tokens"],
            completion_tokens=usage_data["completion_tokens"],
            total_tokens=usage_data["total_tokens"],
            prompt_cost=costs["prompt_cost"],
            completion_cost=costs["completion_cost"],
            total_cost=costs["total_cost"],
            model=model_name,
            cache_hit=cache_hit
        )

        self.add_usage(token_usage)


        usage_output = {
            "success": True,
            "formatter": "api_usage",
            "cost": token_usage.total_cost,
            "model": model_name
        }
        try:
            asyncio.get_event_loop().run_until_complete(
                output_manager.handle_tool_output("api_usage", usage_output)
            )
        except RuntimeError:

            pass

    async def generate_response(self, conversation_history: List[Dict]) -> str:

        try:

            model_info = self.get_model_info(self.default_model)
            if model_info and not model_info.prefers_separate_system_prompt:

                combined_content = ""
                for msg in conversation_history:
                    if msg.get("content"):
                        combined_content += msg["content"] + "\n"

                if not combined_content.strip():
                    combined_content = "Hello, please respond."

                conversation_history = [{"role": "user", "content": combined_content.strip()}]

            response = await self.get_response(
                prompt=None,
                system=None,
                conversation_history=conversation_history,
                temperature=0.5,
                max_tokens=4096
            )

            if response is None:
                return "I encountered an error generating a response. Please try again."

            return response
        except Exception as e:
            logger.error(f"Error in generate_response: {str(e)}")
            return f"I encountered an error generating a response: {str(e)}"

    async def check_for_user_input_request(self, response: str) -> Tuple[bool, Optional[str]]:

        return False, None

    async def get_response(
        self,
        prompt: Optional[str],
        system: Optional[str],
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False,
        model: Optional[str] = None,
        extended_thinking: bool = False,
        thinking_budget: int = 0
    ) -> Optional[str]:

        try:

            model_name = model or self.default_model
            model_info = self.get_model_info(model_name)

            if model_info and tool_usage and not model_info.supports_reasoning:

                for m in self.models.values():
                    if m.supports_reasoning:
                        model_name = m.api_name
                        model_info = m
                        logger.info(f"Switching to reasoning-capable model: {model_name}")
                        break


            if conversation_history:
                messages = conversation_history
            else:
                messages = []
                if system and (not model_info or model_info.prefers_separate_system_prompt):

                    messages.append({"role": "system", "content": system})
                    if prompt:
                        messages.append({"role": "user", "content": prompt})
                else:

                    combined_prompt = (system + "\n\n" + prompt) if system and prompt else (system or prompt or "")
                    if combined_prompt:
                        messages.append({"role": "user", "content": combined_prompt})


            api_model_name = model_info.api_name if model_info else model_name


            thinking_config = None
            if extended_thinking and (thinking_budget > 0 or thinking_budget == -1):

                if model_info and model_info.supports_reasoning:

                    budget = thinking_budget if thinking_budget > 0 else 1024

                    budget = min(budget, max_tokens - 1024)
                    thinking_config = {
                        "type": "enabled",
                        "budget_tokens": budget
                    }
                    logger.debug(f"Enabling reasoning/extended thinking with budget of {budget} tokens")
                else:
                    logger.warning(f"Extended thinking requested but not supported by model {model_name}")


            logger.debug(f"Sending request to LLM with {len(messages)} messages using model {api_model_name}")
            response = await self._make_api_call(
                messages,
                api_model_name,
                temperature,
                max_tokens,
                tool_usage,
                thinking_config
            )


            usage_data, cache_hit, cache_write = self.extract_usage_data(response, api_model_name)
            self.track_usage(usage_data, api_model_name, cache_hit, cache_write)


            return self.extract_response_content(response)

        except Exception as e:
            logger.error(f"API call failed: {str(e)}", exc_info=True)
            return None

    async def _make_api_call(
        self,
        messages: List[Dict],
        model_name: str,
        temperature: float,
        max_tokens: int,
        tool_usage: bool,
        thinking_config: Optional[Dict] = None
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


            if thinking_config and "claude" in model_name.lower():
                params["thinking"] = thinking_config

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

            combined_prompt = system_prompt + "\n\n" + user_prompt if system_prompt else user_prompt
            return None, combined_prompt
        return system_prompt, user_prompt


class DummyLLMClient(BaseLLMClient):
    def __init__(self):

        self.client = type('DummyClient', (), {
            'messages': type('DummyMessages', (), {
                'create': self._dummy_message_create
            }),
            'beta': type('DummyBeta', (), {
                'messages': type('DummyBetaMessages', (), {
                    'create': self._dummy_beta_message_create
                })
            }),
            'chat': type('DummyChat', (), {
                'completions': type('DummyCompletions', (), {
                    'create': self._dummy_completion_create
                })
            })
        })


        self.usage_history = []
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        self.models = {}
        self.default_model = "dummy"
        self.max_model_tokens = 128000


        self.use_token_efficient_tools = False

        self._register_models()

    def _dummy_message_create(self, **kwargs):

        return type('DummyResponse', (), {
            'content': 'This is a dummy response for testing',
            'usage': type('DummyUsage', (), {
                'input_tokens': 10,
                'output_tokens': 10
            }),
            'model': kwargs.get('model', 'dummy'),
            'type': 'message',
            'role': 'assistant',
            'stop_reason': 'end_turn'
        })

    def _dummy_beta_message_create(self, **kwargs):

        return self._dummy_message_create(**kwargs)

    def _dummy_completion_create(self, **kwargs):

        message = type('DummyMessage', (), {
            'content': 'This is a dummy response for testing',
            'role': 'assistant'
        })

        choice = type('DummyChoice', (), {
            'message': message,
            'finish_reason': 'stop',
            'index': 0
        })

        return type('DummyResponse', (), {
            'choices': [choice],
            'usage': type('DummyUsage', (), {
                'prompt_tokens': 10,
                'completion_tokens': 10,
                'total_tokens': 20
            }),
            'model': kwargs.get('model', 'dummy')
        })

    def _initialize_client(self, api_key: str) -> None:

        pass

    def _register_models(self) -> None:
        self.models = {
            "dummy": ModelInfo(
                name="Dummy Model",
                api_name="dummy",
                supports_reasoning=True,
                prefers_separate_system_prompt=True,
                context_window=128000,
                input_price=0.0,
                output_price=0.0
            ),
            "claude-3-7-sonnet": ModelInfo(
                name="Claude 3.7 Sonnet",
                api_name="claude-3-7-sonnet-20250219",
                supports_reasoning=True,
                prefers_separate_system_prompt=True,
                context_window=200000,
                input_price=3.0,
                output_price=15.0
            ),
            "deepseek-reasoner": ModelInfo(
                name="DeepSeek Reasoner",
                api_name="deepseek-reasoner",
                supports_reasoning=True,
                prefers_separate_system_prompt=True,
                context_window=128000,
                input_price=0.0,
                output_price=0.0
            )
        }
        self.default_model = "dummy"


    def _get_tool_schema(self) -> List[Dict[str, Any]]:
        return [{
            "name": "tool_use",
            "description": "Call a tool with the given input to get a result.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the tool to use."
                    },
                    "input": {
                        "type": "object",
                        "description": "The input parameters for the tool."
                    }
                },
                "required": ["name"]
            }
        }]

    async def get_response(self, prompt: Optional[str], system: Optional[str], **kwargs) -> str:
        return "Dummy response."

    async def generate_response(self, conversation_history: List[Dict]) -> str:
        return "Agent session ended."

    def get_model_pricing(self, model_name: str) -> Dict[str, float]:
        return {"input": 0.0, "output": 0.0}
