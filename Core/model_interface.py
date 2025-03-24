import os
import json
import importlib
import traceback
from typing import List, Dict, Any, Optional, Callable, Generator, Union
from abc import ABC, abstractmethod

class ModelInterface(ABC):
    """
    Abstract base class for language model interfaces.
    Implementations should handle the specifics of interacting with different model providers.
    """
    
    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> str:
        """
        Generate a response from the model given a list of messages.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The model's response as a string
        """
        pass
    
    @abstractmethod
    def generate_streaming(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> Generator[str, None, None]:
        """
        Generate a streaming response from the model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Yields:
            Chunks of the model's response as they become available
        """
        pass


class OpenAIModelInterface(ModelInterface):
    """
    Interface for OpenAI models.
    """
    
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        """
        Initialize the OpenAI model interface.
        
        Args:
            model_name: The name of the model to use
            api_key: OpenAI API key (optional, defaults to OPENAI_API_KEY environment variable)
        """
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        
        try:
            # Import the OpenAI library
            import openai
            self.client = openai.OpenAI(api_key=self.api_key)
        except ImportError:
            print("OpenAI library not found. Please install it with 'pip install openai'")
            raise
    
    def generate(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> str:
        """
        Generate a response from the OpenAI model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The model's response as a string
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating from OpenAI: {str(e)}")
            return f"Error: {str(e)}"
    
    def generate_streaming(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> Generator[str, None, None]:
        """
        Generate a streaming response from the OpenAI model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Yields:
            Chunks of the model's response as they become available
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=max_tokens,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"Error: {str(e)}"


class AnthropicModelInterface(ModelInterface):
    """
    Interface for Anthropic models.
    """
    
    def __init__(self, model_name: str, api_key: Optional[str] = None):
        """
        Initialize the Anthropic model interface.
        
        Args:
            model_name: The name of the model to use (e.g., "claude-3-opus-20240229")
            api_key: Anthropic API key (optional, defaults to ANTHROPIC_API_KEY environment variable)
        """
        self.model_name = model_name
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        
        if not self.api_key:
            raise ValueError("Anthropic API key is required. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter.")
        
        try:
            # Import the Anthropic library
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
        except ImportError:
            print("Anthropic library not found. Please install it with 'pip install anthropic'")
            raise
    
    def generate(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> str:
        """
        Generate a response from the Anthropic model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The model's response as a string
        """
        try:
            # Convert messages to Anthropic format if needed
            anthropic_messages = self._convert_messages(messages)
            
            response = self.client.messages.create(
                model=self.model_name,
                messages=anthropic_messages,
                max_tokens=max_tokens
            )
            
            return response.content[0].text
        except Exception as e:
            print(f"Error generating from Anthropic: {str(e)}")
            return f"Error: {str(e)}"
    
    def generate_streaming(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> Generator[str, None, None]:
        """
        Generate a streaming response from the Anthropic model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Yields:
            Chunks of the model's response as they become available
        """
        try:
            # Convert messages to Anthropic format if needed
            anthropic_messages = self._convert_messages(messages)
            
            stream = self.client.messages.create(
                model=self.model_name,
                messages=anthropic_messages,
                max_tokens=max_tokens,
                stream=True
            )
            
            for chunk in stream:
                if chunk.type == "content_block_delta" and hasattr(chunk, "delta") and hasattr(chunk.delta, "text"):
                    yield chunk.delta.text
        except Exception as e:
            yield f"Error: {str(e)}"
    
    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Convert standard messages format to Anthropic format if needed.
        
        Args:
            messages: A list of message dictionaries
            
        Returns:
            Messages in Anthropic format
        """
        # Extract system message if present
        system_message = None
        other_messages = []
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                # Map 'assistant' to 'assistant' and everything else to 'user'
                role = "assistant" if msg["role"] == "assistant" else "user"
                other_messages.append({"role": role, "content": msg["content"]})
        
        # If there's a system message, add it as a system param
        if system_message and len(other_messages) > 0:
            return other_messages
        
        return other_messages


class ExampleModelInterface(ModelInterface):
    """
    Interface for Example models - simple implementation for demonstration purposes.
    """
    
    def __init__(self, model_name: str):
        """
        Initialize the Example model interface.
        
        Args:
            model_name: The name of the model to use
        """
        self.model_name = model_name
        print(f"Initialized Example Model Interface with model: {model_name}")
    
    def generate(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> str:
        """
        Generate a response from the Example model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Returns:
            The model's response as a string
        """
        try:
            # Extract the user's most recent message
            user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
            last_user_message = user_messages[-1] if user_messages else "No user message found."
            
            # Generate a simple response based on the user's message
            response = f"I'm the Example {self.model_name} model responding to: '{last_user_message}'\n\n"
            response += "This is a demonstration response. In a real implementation, I would call an actual LLM API."
            
            return response
        except Exception as e:
            print(f"Error generating from Example model: {str(e)}")
            return f"Error: {str(e)}"
    
    def generate_streaming(self, messages: List[Dict[str, str]], max_tokens: int = 2000) -> Generator[str, None, None]:
        """
        Generate a streaming response from the Example model.
        
        Args:
            messages: A list of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum number of tokens to generate
            
        Yields:
            Chunks of the model's response as they become available
        """
        try:
            # Extract the user's most recent message
            user_messages = [msg["content"] for msg in messages if msg["role"] == "user"]
            last_user_message = user_messages[-1] if user_messages else "No user message found."
            
            # Generate a simple response based on the user's message
            response = f"I'm the Example {self.model_name} model responding to: '{last_user_message}'\n\n"
            response += "This is a demonstration response. In a real implementation, I would call an actual LLM API."
            
            # Simulate streaming by yielding one word at a time
            words = response.split()
            for word in words:
                yield word + " "
                import time
                time.sleep(0.05)  # Add a small delay to simulate streaming
        except Exception as e:
            yield f"Error: {str(e)}"


def get_model_interface(provider: str, model_name: str) -> ModelInterface:
    """
    Factory function to get a model interface based on the provider.
    
    Args:
        provider: The model provider (e.g., "openai", "anthropic", "example")
        model_name: The name of the model
        
    Returns:
        A model interface instance
    """
    provider = provider.lower()
    
    if provider == "openai":
        return OpenAIModelInterface(model_name)
    elif provider == "anthropic":
        return AnthropicModelInterface(model_name)
    elif provider == "example":
        return ExampleModelInterface(model_name)
    elif provider == "gemini":
        # Dynamically import and instantiate GeminiModelInterface
        try:
            from .gemini_interface import GeminiModelInterface
            return GeminiModelInterface(model_name)
        except (ImportError, ModuleNotFoundError):
            raise ValueError("Gemini interface not available. Please install the required dependencies.")
    elif provider == "deepseek":
        # Dynamically import and instantiate DeepSeekModelInterface
        try:
            from .deepseek_interface import DeepSeekModelInterface
            return DeepSeekModelInterface(model_name)
        except (ImportError, ModuleNotFoundError):
            raise ValueError("DeepSeek interface not available. Please install the required dependencies.")
    else:
        raise ValueError(f"Unsupported model provider: {provider}")


if __name__ == "__main__":
    # Simple test
    import os
    
    # Set up a simple test of the OpenAI interface if API key is available
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if openai_api_key:
        try:
            model = get_model_interface("openai", "gpt-3.5-turbo")
            response = model.generate([
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, who are you?"}
            ])
            print(f"OpenAI response: {response}")
        except Exception as e:
            print(f"OpenAI test failed: {str(e)}")
    
    # Set up a simple test of the Anthropic interface if API key is available
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_api_key:
        try:
            model = get_model_interface("anthropic", "claude-3-haiku-20240307")
            response = model.generate([
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello, who are you?"}
            ])
            print(f"Anthropic response: {response}")
        except Exception as e:
            print(f"Anthropic test failed: {str(e)}") 