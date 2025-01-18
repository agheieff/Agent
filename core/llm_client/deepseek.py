# core/llm_client/deepseek.py
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
        temperature: float = 0.5,
        max_tokens: int = 4096
    ) -> Optional[str]:
        try:
            messages = conversation_history if conversation_history else []
            if system:
                messages.insert(0, {"role": "system", "content": system})
            if prompt:
                messages.append({"role": "user", "content": prompt})

            logger.debug(f"Sending request to DeepSeek with {len(messages)} messages")
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            if response.choices and len(response.choices) > 0:
                return response.choices[0].message.content
                
            logger.warning("Received empty response from DeepSeek")
            return None
                    
        except Exception as e:
            logger.error(f"DeepSeek API call failed: {str(e)}", exc_info=True)
            return None
