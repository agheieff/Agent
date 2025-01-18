import aiohttp
import logging
from typing import Optional, List, Dict
from .base import BaseLLMClient

logger = logging.getLogger(__name__)

class DeepSeekClient(BaseLLMClient):
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        self.api_key = api_key
        self.api_url = "https://api.deepseek.com/chat/completions"
        
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

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("choices") and len(result["choices"]) > 0:
                            return result["choices"][0].get("message", {}).get("content")
                    logger.error(f"DeepSeek API error: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"DeepSeek API call failed: {str(e)}")
            return None
