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
        prompt: Optional[str],
        system: Optional[str],
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False
    ) -> Optional[str]:
        """
        Modified so that if 'conversation_history' is provided,
        we do NOT forcibly insert system/prompt again. 
        If conversation_history is empty, we build it from system/prompt.
        """
        try:
            if conversation_history:
                messages = conversation_history
            else:
                messages = []
                if system:
                    messages.append({"role": "system", "content": system})
                if prompt:
                    messages.append({"role": "user", "content": prompt})

            logger.debug(f"Sending request to Claude with {len(messages)} messages")

            # Example/hypothetical usage of the anthropic library:
            # (Placeholder model name below)
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                temperature=temperature,
                system="",    # We'll rely on the 'messages' structure
                messages=messages
            )
            
            # Hypothetical parsing (the real client usage may differ)
            if isinstance(message.content, list) and len(message.content) > 0:
                return message.content[0].text
            elif isinstance(message.content, str):
                # In some versions, .content might be a direct string
                return message.content
            
            logger.warning("Received empty response from Claude")
            return None
            
        except Exception as e:
            logger.error(f"API call failed: {str(e)}", exc_info=True)
            return None

