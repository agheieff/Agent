import logging
import re
from typing import Optional, List, Dict, Any, Tuple
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
        prompt: Optional[str],
        system: Optional[str],
        conversation_history: List[Dict] = None,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        tool_usage: bool = False
    ) -> Optional[str]:
        """
        Modified so that if 'conversation_history' is provided,
        we do NOT forcibly insert system or user from prompt/system.
        That helps avoid repeated or "successive" user/system messages.
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

            logger.debug(f"Sending request to DeepSeek-Reasoner with {len(messages)} messages")
            
            if tool_usage:
                # Hypothetical approach for function calling or tool usage
                response = self.client.chat.completions.create(
                    model="deepseek-reasoner-tools",
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    functions=[{
                        "name": "my_tool",
                        "description": "Example tool usage placeholder",
                        "parameters": {}
                    }],
                    function_call="auto"
                )
            else:
                response = self.client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature
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
            
    async def check_for_user_input_request(self, response: str) -> Tuple[bool, Optional[str]]:
        """
        Check if the model is requesting user input in its response.
        
        Looks for special tags or patterns like <user_input> or [PAUSE_FOR_USER_INPUT].
        
        Args:
            response: The model's response text
            
        Returns:
            Tuple of (should_pause, question_for_user)
        """
        # Look for user input tags
        input_tags = [
            r"<user_input>(.*?)</user_input>",
            r"\[PAUSE_FOR_USER_INPUT\](.*?)\[/PAUSE_FOR_USER_INPUT\]",
            r"\[USER_INPUT\](.*?)\[/USER_INPUT\]",
            r"\[PROMPT_USER\](.*?)\[/PROMPT_USER\]"
        ]
        
        for tag_pattern in input_tags:
            matches = re.finditer(tag_pattern, response, re.DOTALL)
            for match in matches:
                # Extract the question to ask the user
                question = match.group(1).strip() if match.group(1) else "Please provide additional information:"
                logger.info(f"Detected user input request: {question}")
                return True, question
        
        # Also check for more explicit phrases
        explicit_phrases = [
            "I need more information from you to proceed",
            "I need to ask you a question before continuing", 
            "Please provide more details so I can continue",
            "I'll pause here and wait for your input",
            "Could you clarify",
            "Could you provide more details about"
        ]
        
        for phrase in explicit_phrases:
            if phrase in response:
                # Extract a sentence containing the phrase
                sentences = re.split(r'(?<=[.!?])\s+', response)
                for sentence in sentences:
                    if phrase in sentence:
                        logger.info(f"Detected implicit user input request: {sentence}")
                        return True, sentence
        
        # No input request found
        return False, None
