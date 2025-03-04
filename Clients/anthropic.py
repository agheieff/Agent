import anthropic
import logging
import json
from typing import Dict, List, Any, Optional
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str, use_token_efficient_tools: bool = True):
        self.use_token_efficient_tools = use_token_efficient_tools
        super().__init__(api_key)

    def _initialize_client(self, api_key: str) -> None:
        if not api_key:
            logger.error("Empty API key provided for Anthropic client")
            raise ValueError("API key cannot be empty")
        try:
            self.client = anthropic.Client(api_key=api_key)
            logger.info("Anthropic client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Anthropic client: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to initialize Anthropic client: {str(e)}")

    def _register_models(self) -> None:
        claude_sonnet = ModelInfo(
            name="Claude 3.7 Sonnet",
            api_name="claude-3-7-sonnet-20250219",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=200000,
            input_price=3.0,
            output_price=15.0,
            input_cache_read_price=0.30,
            input_cache_write_price=3.75
        )
        self.models["claude-3-7-sonnet"] = claude_sonnet
        self.default_model = "claude-3-7-sonnet"

    def _make_api_call(
        self,
        messages: List[Dict],
        model_name: str,
        temperature: float,
        max_tokens: int,
        tool_usage: bool,
        thinking_config: Optional[Dict] = None
    ) -> Any:

        if not hasattr(self, 'client'):
            raise ValueError("Anthropic client not initialized")

        prompt_text = self._convert_messages_to_prompt(messages)
        params = {
            "prompt": prompt_text,
            "model": model_name,
            "max_tokens_to_sample": max_tokens,
            "temperature": temperature
        }
        return self.client.completions.create(**params)

    def _convert_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        conversation_text = []
        for m in messages:
            role = m.get("role", "user").lower()
            content = m.get("content", "")
            if role == "system":

                conversation_text.append(f"[System]: {content}\n")
            elif role == "assistant":
                conversation_text.append(f"[Assistant]: {content}\n")
            else:
                conversation_text.append(f"[User]: {content}\n")
        return "\n".join(conversation_text)

