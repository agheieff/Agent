import logging
from typing import Optional, List, Dict, Any
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
        max_tokens: int = 4096,
        tool_usage: bool = False
    ) -> Optional[str]:
        """
        Example of how we might handle 'tool_usage' in an OpenAI-like client.
        If tool_usage is True, we do a hypothetical function calling approach.
        """
        try:
            messages = conversation_history if conversation_history else []
            if system:
                messages.insert(0, {"role": "system", "content": system})
            if prompt:
                messages.append({"role": "user", "content": prompt})

            logger.debug(f"Sending request to DeepSeek-Reasoner with {len(messages)} messages")
            
            if tool_usage:
                # Hypothetical approach for function calling or tool usage:
                # The real logic would differ depending on the API.
                # We place a placeholder to illustrate where you'd handle it:
                response = self.client.chat.completions.create(
                    model="deepseek-reasoner-tools",
                    messages=messages,
                    max_tokens=max_tokens,
                    functions=[{
                        "name": "my_tool",
                        "description": "Example tool usage placeholder",
                        "parameters": {}
                    }],
                    function_call="auto"
                )
                
                # The user would parse out function calls from 'response' here.
                # This is purely illustrative.
            else:
                response = self.client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=messages,
                    max_tokens=max_tokens
                )
            
            if response.choices and len(response.choices) > 0:
                message = response.choices[0].message
                # Some models might separate a 'reasoning_content'
                # For now we assume it might exist:
                reasoning_content = getattr(message, 'reasoning_content', None)
                content = message.content
                
                # Log reasoning chain for debugging if present
                if reasoning_content:
                    logger.debug(f"Reasoning Chain:\n{reasoning_content}")
                
                return content
                
            logger.warning("Received empty response from DeepSeek-Reasoner")
            return None
                    
        except Exception as e:
            logger.error(f"DeepSeek-Reasoner API call failed: {str(e)}", exc_info=True)
            return None
