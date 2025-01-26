import logging
from typing import Optional, List, Dict
from openai import OpenAI
from .base import BaseLLMClient

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
    async def get_response(
        self,
        prompt: str,
        system: str,
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,  # Parameter kept for interface compatibility
        max_tokens: int = 4096
    ) -> Optional[str]:
        try:
            messages = conversation_history if conversation_history else []
            if system:
                messages.insert(0, {"role": "system", "content": system})
            if prompt:
                messages.append({"role": "user", "content": prompt})

            logger.debug(f"Sending request to DeepSeek-Reasoner with {len(messages)} messages")
            response = self.client.chat.completions.create(
                model="deepseek-reasoner",
                messages=messages,
                max_tokens=max_tokens
            )
            
            if response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                reasoning_content = message.reasoning_content
                content = message.content
                
                # Log reasoning chain for debugging
                logger.debug(f"Reasoning Chain:\n{reasoning_content}")
                
                return content
                
            logger.warning("Received empty response from DeepSeek-Reasoner")
            return None
                    
        except Exception as e:
            logger.error(f"DeepSeek-Reasoner API call failed: {str(e)}", exc_info=True)
            return None
