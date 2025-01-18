import anthropic
import logging
from typing import Optional, List, Dict
from .base import BaseLLMClient

logger = logging.getLogger(__name__)

class AnthropicClient(BaseLLMClient):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Anthropic API key is required")
        self.client = anthropic.Anthropic(api_key=api_key)
        
    async def get_response(
        self,
        prompt: str,
        system: str,
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096
    ) -> Optional[str]:
        try:
            messages = conversation_history if conversation_history else []
            if prompt:
                messages.append({"role": "user", "content": prompt})
            
            logger.debug(f"Sending request to Claude with {len(messages)} messages")
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=messages
            )
            
            if isinstance(message.content, list) and len(message.content) > 0:
                return message.content[0].text
            logger.warning("Received empty response from Claude")
            return None
            
        except Exception as e:
            logger.error(f"API call failed: {str(e)}", exc_info=True)
            return None
