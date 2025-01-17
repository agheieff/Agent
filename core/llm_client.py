# core/llm_client.py
import anthropic
from typing import Optional, List, Dict

class AnthropicClient:
    def __init__(self, api_key: Optional[str] = None):
        self.client = anthropic.Anthropic(api_key=api_key)
        
    async def get_response(
        self, 
        prompt: str, 
        system: str,
        conversation_history: List[Dict] = None
    ) -> str:
        """Send a prompt to Claude with conversation history."""
        messages = []
        
        if conversation_history:
            messages.extend(conversation_history)
            
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                temperature=0.5,
                system=system,
                messages=messages
            )
            # Convert the response content to string
            return str(message.content)
        except Exception as e:
            print(f"API call failed: {e}")
            return None
