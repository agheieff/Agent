# core/llm_client.py
import anthropic
from typing import Optional, List, Dict

class AnthropicClient:
    def __init__(self, api_key: Optional[str] = None):
        if not api_key:
            raise ValueError("Anthropic API key is required")
        self.client = anthropic.Anthropic(api_key=api_key)
        
    async def get_response(
        self, 
        prompt: str, 
        system: str,
        conversation_history: List[Dict] = None
    ) -> str:
        """Send a prompt to Claude with conversation history."""
        try:
            # For Messages API, we use the conversation history directly
            messages = conversation_history if conversation_history else []
            
            # Only append the prompt if it's not empty (which it should be in our case)
            if prompt:
                messages.append({
                    "role": "user",
                    "content": prompt
                })
            
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                temperature=0.5,
                system=system,
                messages=messages
            )
            
            # The Messages API returns content as a list of content blocks
            # For our use case, we know it's text, so we extract it
            if isinstance(message.content, list) and len(message.content) > 0:
                return message.content[0].text
            return ""
            
        except Exception as e:
            print(f"API call failed: {e}")
            return None
