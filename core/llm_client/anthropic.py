import anthropic
import logging
import re
from typing import Optional, List, Dict, Tuple
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

