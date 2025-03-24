import os
import logging
from typing import Dict, List, Optional, Any

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google's Generative AI package not found. Install with 'pip install google-generativeai'")

from Clients.base import BaseClient, Message, ModelConfig, PromptStyle, PricingTier

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GeminiClient(BaseClient):
    """Client for Google's Gemini API."""

    def __init__(self, api_key=None, api_base=None):
        """Initialize the client with API key."""
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.api_base = api_base
        
        # Initialize client before parent initialization
        self.genai = None
        if GEMINI_AVAILABLE and self.api_key:
            self.genai = genai
            self.genai.configure(api_key=self.api_key)
        
        super().__init__(api_key=self.api_key, api_base=self.api_base)
                
    def _get_model_configs(self) -> Dict[str, ModelConfig]:
        """Get model configurations for all supported Gemini models."""
        return {
            "gemini-pro": ModelConfig(
                name="gemini-pro",
                prompt_style=PromptStyle.PREPEND_TO_USER,
                context_length=32768,
                pricing=PricingTier(input=0.00025, output=0.0005),
            ),
            "gemini-1.5-pro": ModelConfig(
                name="gemini-1.5-pro",
                prompt_style=PromptStyle.PREPEND_TO_USER,
                context_length=1000000,
                pricing=PricingTier(input=0.00035, output=0.00105),
            ),
            "gemini-1.5-flash": ModelConfig(
                name="gemini-1.5-flash",
                prompt_style=PromptStyle.PREPEND_TO_USER,
                context_length=1000000,
                pricing=PricingTier(input=0.000175, output=0.000525),
            ),
            "gemini-pro-vision": ModelConfig(
                name="gemini-pro-vision",
                prompt_style=PromptStyle.PREPEND_TO_USER,
                context_length=32768,
                pricing=PricingTier(input=0.0025, output=0.005),
            ),
        }
    
    def _get_default_model(self) -> str:
        """Get the default model for Gemini."""
        return "gemini-1.5-pro"
    
    def _chat_completion_provider(self, messages, model, temperature=0.7, max_tokens=None, stream=False):
        if not self.genai:
            raise Exception("Google Generative AI package is required. Install with 'pip install google-generativeai'")
            
        gemini_messages = []
        for msg in messages:
            if msg.role == "system":
                continue
            
            role = "model" if msg.role == "assistant" else "user"
            gemini_messages.append({"role": role, "parts": [msg.content]})
            
        model_obj = self.genai.GenerativeModel(model_name=self.get_model_config(model).name)
        
        chat = model_obj.start_chat(history=gemini_messages)
        
        generation_config = {
            "temperature": temperature
        }
        
        if max_tokens:
            generation_config["max_output_tokens"] = max_tokens
                
        with self.rate_limiter:
            if stream:
                response = chat.send_message(
                    "",
                    generation_config=generation_config,
                    stream=True
                )
                return response
            else:
                response = chat.send_message(
                    "",
                    generation_config=generation_config
                )
                
                content_length = len(response.text)
                total_message_length = sum(len(msg.content) for msg in messages)
                
                prompt_tokens = int(total_message_length / 4)
                completion_tokens = int(content_length / 4)
                
                self._update_usage_stats({
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }, model)
                
                return response
    
    def chat_completion(self, messages, model=None, system_prompt=None,
                       temperature=0.7, max_tokens=None, stream=False):
        """Generate a chat completion."""
        # Use default model if none provided
        model = model or self._get_default_model()
        
        return self._chat_completion_provider(messages, model, temperature, max_tokens, stream)
    
    def text_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stream: bool = False,
        system_prompt: Optional[str] = None,
    ) -> Any:
        """Generate a text completion using Gemini's API"""
        # Gemini doesn't differentiate between chat and text completion
        messages = [Message(role="user", content=prompt)]
        
        return self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            system_prompt=system_prompt,
        )
    
    def embeddings(
        self,
        input_texts: List[str],
        model: Optional[str] = "embedding-001",
    ) -> List[List[float]]:
        """Generate embeddings for input texts"""
        model = model or "embedding-001"
        model_config = self.get_model_config(model)
        
        if not self.genai:
            raise Exception("Google Generative AI package is required. Install with 'pip install google-generativeai'")
        
        embeddings = []
        total_chars = 0
        
        # Process each text
        with self.rate_limiter:
            for text in input_texts:
                embedding_model = self.genai.get_embedding_model(model_config.name)
                result = embedding_model.embed_content(text)
                
                embeddings.append(result.embedding)
                total_chars += len(text)
            
            # Estimate token count (Gemini doesn't provide it for embeddings)
            estimated_tokens = int(total_chars / 4)
            
            # Update usage statistics
            self._update_usage_stats({
                "prompt_tokens": estimated_tokens,
                "completion_tokens": 0,
            }, model)
            
            return embeddings 