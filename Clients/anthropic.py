from typing import Dict, List, Any, Optional
import logging
import anthropic
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
        m = ModelInfo("Claude 3.7 Sonnet", "claude-3-7-sonnet-20250219", True, True, 200000, 3.0, 15.0, 0.30, 3.75)
        self.models["claude-3-7-sonnet"] = m
        self.default_model = "claude-3-7-sonnet"
    async def _make_api_call(self, m: List[Dict], mn: str, temperature: float, max_tokens: int, tool_usage: bool) -> Any:
        if not hasattr(self, "client"):
            raise ValueError("Anthropic client not initialized")
        p = self._convert_messages_to_prompt(m)
        d = {"prompt": p, "model": mn, "max_tokens_to_sample": max_tokens, "temperature": temperature}
        return self.client.completions.create(**d)
    def _convert_messages_to_prompt(self, m: List[Dict[str, str]]) -> str:
        c = []
        for x in m:
            r = x.get("role", "user").lower()
            t = x.get("content") or ""
            if r == "system":
                c.append(f"[System]: {t}\n")
            elif r == "assistant":
                c.append(f"[Assistant]: {t}\n")
            else:
                c.append(f"[User]: {t}\n")
        return "\n".join(c)
