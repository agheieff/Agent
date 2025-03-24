import os
import logging
from typing import Dict, List, Optional, Any

try:
    import openai
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI Python package not found. Install with 'pip install openai'")

try:
    import deepseek
except ImportError:
    logging.warning("DeepSeek Python package not found. Install with 'pip install deepseek-ai'")

from Clients.base import BaseClient, Message, ModelConfig, PromptStyle, PricingTier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeepSeekClient(BaseClient):
    def __init__(self, api_key=None, api_base=None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.api_base = api_base or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        
        self.client = None
        if OPENAI_AVAILABLE and self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        
        super().__init__(api_key=self.api_key, api_base=self.api_base)
                
    def _get_model_configs(self) -> Dict[str, ModelConfig]:
        return {
            "deepseek-chat": ModelConfig(
                name="deepseek-chat",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=32768,
                pricing=PricingTier(input=0.0005, output=0.0025),
            ),
            "deepseek-coder": ModelConfig(
                name="deepseek-coder",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=32768,
                pricing=PricingTier(input=0.001, output=0.005),
            ),
            "deepseek-reasoner": ModelConfig(
                name="deepseek-reasoner",
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=32768,
                pricing=PricingTier(input=0.0015, output=0.006),
            ),
            "deepseek-rl": ModelConfig(
                name="deepseek-rl", 
                prompt_style=PromptStyle.SYSTEM_MESSAGE,
                context_length=32768,
                pricing=PricingTier(input=0.0008, output=0.0032),
            )
        }
    
    def _get_default_model(self) -> str:
        return "deepseek-chat"
    
    def _chat_completion_provider(self, messages, model, temperature=0.7, max_tokens=None, stream=False):
        if not self.client:
            raise Exception("OpenAI package is required. Install with 'pip install openai'")
            
        openai_messages = []
        for msg in messages:
            if msg.role == "function":
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.function_call_id,
                })
            else:
                openai_message = {"role": msg.role, "content": msg.content}
                if msg.name:
                    openai_message["name"] = msg.name
                    
                openai_messages.append(openai_message)
            
        kwargs = {
            "model": self.get_model_config(model).name,
            "messages": openai_messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
                
        with self.rate_limiter:
            if stream:
                return self.client.chat.completions.create(**kwargs)
            else:
                response = self.client.chat.completions.create(**kwargs)
                
                if hasattr(response, "usage"):
                    self._update_usage_stats({
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                    }, model)
                
                return response
    
    def chat_completion(self, messages, model=None, system_prompt=None,
                       temperature=0.7, max_tokens=None, stream=False, discard_reasoning=False):
        """Generate a chat completion."""
        # Use default model if none provided
        model = model or self._get_default_model()
        
        if not self.client:
            raise Exception("OpenAI package is required. Install with 'pip install openai'")
            
        # Handle system prompt
        processed_messages = self._handle_system_prompt(messages, system_prompt, model)
            
        # Convert messages to OpenAI format
        openai_messages = []
        for msg in processed_messages:
            if msg.role == "function":
                # OpenAI expects "function" messages as "tool" messages in the API
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.function_call_id,
                })
            else:
                openai_message = {"role": msg.role, "content": msg.content}
                if msg.name:
                    openai_message["name"] = msg.name
                    
                openai_messages.append(openai_message)
            
        # Prepare API call
        kwargs = {
            "model": self.get_model_config(model).name,
            "messages": openai_messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
                
        # Make the API call
        with self.rate_limiter:
            # Handle streaming separately for reasoning extraction
            if stream:
                stream_response = self.client.chat.completions.create(**kwargs)
                
                # Handle reasoning differently for streaming
                if model == "deepseek-reasoner" and discard_reasoning:
                    return self.reasoning_extractor.handle_streaming_chunks(stream_response)
                else:
                    return stream_response
            else:
                response = self.client.chat.completions.create(**kwargs)
                
                # Handle reasoner model content extraction
                if model == "deepseek-reasoner" and discard_reasoning:
                    content = response.choices[0].message.content
                    final_answer = self.reasoning_extractor.extract_final_answer(content)
                    response.choices[0].message.content = final_answer
                
                # Update usage statistics
                if hasattr(response, "usage"):
                    self._update_usage_stats({
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                    }, model)
                
                return response
    
    def get_model_config(self, model_name: str) -> ModelConfig:
        """Get configuration for a specific model"""
        model_name = model_name or self.default_model
        if model_name not in self.models:
            raise ValueError(f"Unknown model: {model_name}")
        return self.models[model_name]
    
    def _convert_to_openai_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Convert internal Message objects to OpenAI format"""
        openai_messages = []
        
        for msg in messages:
            openai_msg: Dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            
            if msg.name:
                openai_msg["name"] = msg.name
                
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
                
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
                
            openai_messages.append(openai_msg)
            
        return openai_messages
    
    def format_system_prompt(self, system_prompt: str, messages: List[Message], model_name: str) -> List[Message]:
        """
        Format the system prompt according to DeepSeek's requirements
        DeepSeek expects the system prompt to be prepended to the first user message
        """
        model_config = self.get_model_config(model_name)
        
        if not messages:
            # If no messages, create a user message with the system prompt
            return [Message(role="user", content=system_prompt)]
        
        # For DeepSeek, we need to prepend system prompt to the first user message
        result = messages.copy()
        
        # Find the first user message
        for i, msg in enumerate(result):
            if msg.role == "user":
                # Prepend system prompt to user message
                result[i] = Message(
                    role="user",
                    content=f"{system_prompt}\n\n{msg.content}",
                    name=msg.name
                )
                break
        
        return result
    
    def text_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        stream: bool = False,
        system_prompt: Optional[str] = None,
        discard_reasoning: bool = False,
    ) -> Any:
        """Generate a text completion using DeepSeek's API"""
        # DeepSeek uses a chat-based API, so we'll convert the text prompt to a message
        messages = [Message(role="user", content=prompt)]
        return self.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            system_prompt=system_prompt,
            discard_reasoning=discard_reasoning,
        )
    
    def embeddings(
        self,
        input_texts: List[str],
        model: Optional[str] = None,
    ) -> List[List[float]]:
        """Generate embeddings for input texts"""
        # DeepSeek does not currently support embeddings through their API
        # This could be updated if/when DeepSeek adds embedding endpoints
        raise NotImplementedError("DeepSeek does not currently provide a public embeddings API") 