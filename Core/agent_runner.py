import os
import sys
import re
import time
import json
import traceback
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
import importlib.util
import inspect
import argparse
from collections import deque
import threading
import queue

# Import tool-related components
from Tools.base import Tool, ErrorCodes
from Core.model_interface import get_model_interface, ModelInterface

# Import system prompt from Prompts module
from Prompts.main import generate_system_prompt

# Import utilities
from Core.utils import get_multiline_input


class AgentConversation:
    """
    Manages the conversation between the user and an agent.
    Handles storing and retrieving messages, maintaining context, and managing tokens.
    """
    
    def __init__(self, max_tokens: int = 8000, context_window: int = 16000):
        """
        Initialize a new conversation.
        
        Args:
            max_tokens: Maximum number of tokens to keep in the conversation history
            context_window: The model's context window size in tokens
        """
        self.messages = []
        self.max_tokens = max_tokens
        self.context_window = context_window
        self.system_prompt = ""
        self._approximate_token_count = 0
        self._conversation_log = []  # Separate log for saving the complete conversation
    
    def set_system_prompt(self, prompt: str):
        """Set the system prompt for the conversation."""
        self.system_prompt = prompt
    
    def add_user_message(self, content: str):
        """Add a message from the user to the conversation."""
        self._add_message("user", content)
    
    def add_assistant_message(self, content: str):
        """Add a message from the assistant to the conversation."""
        self._add_message("assistant", content)
    
    def add_tool_message(self, tool_name: str, content: str):
        """Add a message from a tool to the conversation."""
        self._add_message("tool", content, tool_name=tool_name)
    
    def _add_message(self, role: str, content: str, **kwargs):
        """
        Add a message to the conversation and the conversation log.
        
        Args:
            role: The role of the message sender (user, assistant, tool)
            content: The content of the message
            **kwargs: Additional message metadata
        """
        message = {"role": role, "content": content, **kwargs, "timestamp": time.time()}
        
        # Add to the log (complete history)
        self._conversation_log.append(message)
        
        # Add to the active conversation (limited by tokens)
        self.messages.append(message)
        
        # Update token count (rough estimate)
        self._approximate_token_count += self._estimate_tokens(content)
        
        # Truncate if necessary
        self._truncate_conversation()
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text string.
        This is a rough approximation based on words/4.
        
        Args:
            text: The text to estimate
            
        Returns:
            Estimated token count
        """
        # Rough approximation: ~4 chars per token for English text
        return len(text) // 4 + 1
    
    def _truncate_conversation(self):
        """
        Truncate the conversation history if it exceeds max_tokens,
        while keeping the system prompt and the most recent messages.
        """
        if self._approximate_token_count <= self.max_tokens:
            return
        
        # Always keep the most recent messages
        preserved_messages = [msg for msg in self.messages if msg["role"] in ["user", "assistant"]][-2:]
        
        # Calculate tokens to keep
        remaining_tokens = self.max_tokens - sum(self._estimate_tokens(msg["content"]) for msg in preserved_messages)
        
        # Start with essential messages (typically the user query and last assistant response)
        new_messages = []
        new_token_count = 0
        
        # Add messages from oldest to newest until we hit the token limit
        for msg in self.messages:
            msg_tokens = self._estimate_tokens(msg["content"])
            
            # Skip if this would exceed our limit, unless it's in the preserved messages
            if new_token_count + msg_tokens > remaining_tokens and msg not in preserved_messages:
                continue
                
            new_messages.append(msg)
            new_token_count += msg_tokens
        
        # Update the message list and token count
        self.messages = new_messages
        self._approximate_token_count = new_token_count
    
    def get_formatted_messages(self) -> List[Dict[str, str]]:
        """
        Get the formatted conversation history suitable for sending to an LLM.
        
        Returns:
            A list of message dictionaries
        """
        formatted_messages = []
        
        # Add system prompt
        if self.system_prompt:
            formatted_messages.append({"role": "system", "content": self.system_prompt})
        
        # Add conversation history
        for msg in self.messages:
            if msg["role"] == "tool":
                # Format tool messages
                formatted_msg = {
                    "role": "tool",
                    "content": msg["content"],
                    "name": msg.get("tool_name", "unknown_tool")
                }
            else:
                # Format user and assistant messages
                formatted_msg = {
                    "role": msg["role"],
                    "content": msg["content"]
                }
            
            formatted_messages.append(formatted_msg)
        
        return formatted_messages
    
    def save_conversation(self, filename: str):
        """
        Save the complete conversation log to a file.
        
        Args:
            filename: The file to save to
        """
        with open(filename, 'w') as f:
            json.dump(self._conversation_log, f, indent=2)
    
    def load_conversation(self, filename: str):
        """
        Load a conversation from a file.
        
        Args:
            filename: The file to load from
        """
        with open(filename, 'r') as f:
            self._conversation_log = json.load(f)
            self.messages = self._conversation_log.copy()
            self._approximate_token_count = sum(self._estimate_tokens(msg["content"]) for msg in self.messages)


class ToolRegistry:
    """
    Registry for managing and executing tools.
    """
    
    def __init__(self):
        """Initialize the tool registry."""
        self.tools = {}
        self.tool_instances = {}
    
    def register_tool(self, tool_class):
        """
        Register a tool class with the registry.
        
        Args:
            tool_class: The tool class to register
        """
        instance = tool_class()
        self.tool_instances[instance.name] = instance
        self.tools[instance.name] = tool_class
    
    def register_tools_from_module(self, module_path: str):
        """
        Register all tools from a module.
        
        Args:
            module_path: The module path to load tools from
        """
        try:
            module = importlib.import_module(module_path)
            
            # Find all Tool subclasses in the module
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, Tool) and obj is not Tool:
                    self.register_tool(obj)
        except ImportError as e:
            print(f"Error importing module {module_path}: {e}")
    
    def register_all_tools(self):
        """Register all tools from the Tools package."""
        # Register file tools
        self.register_tools_from_module("Tools.File")
        
        # Register special tools
        self.register_tools_from_module("Tools.Special")
    
    def is_valid_tool(self, tool_name: str) -> bool:
        """
        Check if a tool name is valid.
        
        Args:
            tool_name: The name of the tool to check
            
        Returns:
            True if the tool exists, False otherwise
        """
        return tool_name in self.tool_instances
    
    def execute_tool(self, tool_name: str, **kwargs) -> Tuple[int, str]:
        """
        Execute a tool with the given arguments.
        
        Args:
            tool_name: The name of the tool to execute
            **kwargs: Arguments to pass to the tool
            
        Returns:
            A tuple containing the error code and result message
        """
        if not self.is_valid_tool(tool_name):
            return ErrorCodes.INVALID_TOOL, f"Tool '{tool_name}' not found"
        
        tool = self.tool_instances[tool_name]
        
        try:
            # Execute the tool
            return tool.execute(**kwargs)
        except Exception as e:
            # Capture and format the exception
            error_msg = f"Error executing tool {tool_name}: {str(e)}\n{traceback.format_exc()}"
            return ErrorCodes.UNKNOWN_ERROR, error_msg
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a tool.
        
        Args:
            tool_name: The name of the tool
            
        Returns:
            A dictionary containing tool information, or None if the tool doesn't exist
        """
        if not self.is_valid_tool(tool_name):
            return None
        
        tool = self.tool_instances[tool_name]
        
        return {
            "name": tool.name,
            "description": tool.description,
            "help_text": tool.help_text,
            "arguments": [
                {
                    "name": arg.name,
                    "type": arg.arg_type.name,
                    "description": arg.description,
                    "is_optional": arg.is_optional,
                    "default_value": arg.default_value
                }
                for arg in tool.arguments
            ]
        }


class AgentRunner:
    """
    Main class for running an agent with tool execution capabilities.
    """
    
    def __init__(self, model_provider: str, model_name: str):
        """
        Initialize the agent runner.
        
        Args:
            model_provider: The provider of the LLM (e.g., "openai")
            model_name: The name of the model to use
        """
        self.model_provider = model_provider
        self.model_name = model_name
        self.conversation = AgentConversation()
        self.tool_registry = ToolRegistry()
        self.tool_registry.register_all_tools()
        self.running = False
        self.output_queue = queue.Queue()
        self.model = None
        
        # Flag for when the end tool is called
        self.conversation_ended = False
    
    def set_system_prompt(self):
        """Set the system prompt based on available tools."""
        system_prompt = generate_system_prompt(provider=self.model_provider)
        self.conversation.set_system_prompt(system_prompt)
    
    def connect_to_model(self):
        """
        Connect to the LLM provider.
        """
        try:
            self.model = get_model_interface(self.model_provider, self.model_name)
            self.output_to_screen(f"Connected to {self.model_provider} using model {self.model_name}", role="system")
        except Exception as e:
            error_msg = f"Error connecting to model: {str(e)}"
            self.output_to_screen(error_msg, role="system")
            raise RuntimeError(error_msg)
    
    def parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from the model's response.
        
        Args:
            response: The raw response from the model
            
        Returns:
            A list of parsed tool calls
        """
        # Simple regex pattern to extract tool calls
        # Format: @tool tool_name param1="value1" param2="value2"
        tool_calls = []
        
        # Match @tool directives
        tool_pattern = r'@tool\s+(\w+)((?:\s+\w+\s*=\s*(?:"[^"]*"|\d+|True|False))*)(?:\n|$)'
        param_pattern = r'(\w+)\s*=\s*(?:"([^"]*)"|(\d+(?:\.\d+)?)|(\w+))'
        
        for match in re.finditer(tool_pattern, response, re.MULTILINE):
            tool_name = match.group(1)
            param_str = match.group(2)
            
            # Extract parameters
            params = {}
            for param_match in re.finditer(param_pattern, param_str):
                param_name = param_match.group(1)
                
                # Determine parameter type and value
                if param_match.group(2) is not None:  # String
                    param_value = param_match.group(2)
                elif param_match.group(3) is not None:  # Number
                    param_value = float(param_match.group(3))
                    # Convert to int if it's a whole number
                    if param_value.is_integer():
                        param_value = int(param_value)
                else:  # Boolean
                    bool_val = param_match.group(4)
                    param_value = bool_val.lower() == "true"
                
                params[param_name] = param_value
            
            tool_calls.append({
                "tool_name": tool_name,
                "parameters": params
            })
        
        return tool_calls
    
    def process_model_response(self, response: str) -> str:
        """
        Process the model's response, executing any tool calls.
        
        Args:
            response: The raw response from the model
            
        Returns:
            The processed response with tool call results
        """
        # Check if response is an error message (starts with "Error:")
        if response.strip().startswith("Error:"):
            # For error responses, just add to conversation without duplicating to screen
            # since get_streaming_response already displayed it
            self.conversation.add_assistant_message(response)
            return response
        
        # Parse tool calls
        tool_calls = self.parse_tool_calls(response)
        
        if not tool_calls:
            # No tool calls, just return the response
            self.conversation.add_assistant_message(response)
            self.output_to_screen(response, role="assistant")
            return response
        
        # Split response into text chunks and tool calls
        parts = re.split(r'(@tool\s+\w+(?:\s+\w+\s*=\s*(?:"[^"]*"|\d+|True|False))*(?:\n|$))', response)
        
        processed_response = ""
        tool_outputs = []
        
        i = 0
        while i < len(parts):
            # Add text before the tool call
            if parts[i]:
                processed_response += parts[i]
            
            # Process tool call if present
            if i + 1 < len(parts) and parts[i + 1].startswith('@tool'):
                tool_call_text = parts[i + 1]
                
                # Find which tool this corresponds to
                for idx, tool_call in enumerate(tool_calls):
                    tool_text = f"@tool {tool_call['tool_name']}"
                    if tool_call_text.startswith(tool_text):
                        # Execute the tool
                        tool_name = tool_call['tool_name']
                        params = tool_call['parameters']
                        
                        # Log the tool call
                        self.output_to_screen(f"Executing tool: {tool_name} with parameters: {params}", role="system")
                        
                        # Execute the tool
                        code, result = self.tool_registry.execute_tool(tool_name, **params)
                        
                        # Handle the end tool specially
                        if tool_name == "end" and code == 999:
                            self.conversation_ended = True
                            break
                        
                        # Add tool output to the conversation
                        self.conversation.add_tool_message(tool_name, result)
                        
                        # Display tool output to the user
                        if code == ErrorCodes.SUCCESS:
                            status = "SUCCESS"
                        else:
                            status = f"ERROR: {code}"
                        
                        self.output_to_screen(f"Tool {tool_name} returned ({status}):\n{result}", role="tool")
                        
                        # Add tool output to the response
                        tool_output = f"\n[Tool {tool_name} output: {result}]\n"
                        processed_response += tool_output
                        tool_outputs.append((tool_name, result))
                        
                        break
                
                # Skip the tool call text since we've processed it
                i += 2
            else:
                i += 1
        
        # Add the processed response to the conversation
        self.conversation.add_assistant_message(processed_response)
        
        # Check if the conversation has ended
        if self.conversation_ended:
            return processed_response
        
        return processed_response
    
    def get_model_response(self, max_tokens: int = 4000) -> str:
        """
        Get a response from the model.
        
        Args:
            max_tokens: Maximum tokens to generate
            
        Returns:
            The model's response
        """
        try:
            messages = self.conversation.get_formatted_messages()
            
            # Handle potential errors in generating a response
            try:
                response = self.model.generate(messages, max_tokens=max_tokens)
                return response
            except Exception as e:
                error_msg = f"Error getting model response: {str(e)}"
                self.output_to_screen(error_msg, role="system")
                return f"I encountered an error: {str(e)}. Please try a different approach or check your inputs."
        
        except Exception as e:
            error_msg = f"Unexpected error in get_model_response: {str(e)}\n{traceback.format_exc()}"
            self.output_to_screen(error_msg, role="system")
            return "I encountered an unexpected error. Please try again or contact support."
    
    def get_streaming_response(self, max_tokens: int = 4000) -> str:
        """
        Get a streaming response from the model, displaying chunks as they arrive.
        
        Args:
            max_tokens: Maximum tokens to generate
            
        Returns:
            The complete response
        """
        try:
            messages = self.conversation.get_formatted_messages()
            
            # Accumulate the full response
            full_response = ""
            
            # Process the streaming response
            for chunk in self.model.generate_streaming(messages, max_tokens=max_tokens):
                # Add to the full response
                full_response += chunk
                
                # Display the chunk to the user
                self.output_queue.put(chunk)
            
            return full_response
        
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.output_to_screen(error_msg, role="assistant")
            return error_msg
    
    def output_to_screen(self, text: str, role: str = "system"):
        """
        Output text to the user's screen without adding it to the conversation.
        
        Args:
            text: The text to output
            role: The role (system, assistant, tool, user)
        """
        # Use different formatting based on the role
        if role == "system":
            formatted = f"\n[SYSTEM] {text}\n"
        elif role == "assistant":
            formatted = f"\n[ASSISTANT] {text}\n"
        elif role == "tool":
            formatted = f"\n[TOOL] {text}\n"
        elif role == "user":
            formatted = f"\n[USER] {text}\n"
        else:
            formatted = f"\n{text}\n"
        
        # Add to the output queue for the display thread
        self.output_queue.put(formatted)
    
    def display_thread_function(self):
        """Thread function for displaying output to the user."""
        while self.running:
            try:
                # Get output with a timeout to allow checking if we're still running
                output = self.output_queue.get(timeout=0.5)
                print(output, end="", flush=True)
                self.output_queue.task_done()
            except queue.Empty:
                # Queue is empty, just continue
                continue
    
    def run(self, initial_prompt: str):
        """
        Run the agent with the given initial prompt.
        
        Args:
            initial_prompt: The initial user prompt
        """
        try:
            # Set up the system prompt
            self.set_system_prompt()
            
            # Connect to the model
            self.connect_to_model()
            
            # Start the display thread
            self.running = True
            display_thread = threading.Thread(target=self.display_thread_function)
            display_thread.daemon = True
            display_thread.start()
            
            # Add the initial prompt to the conversation
            self.conversation.add_user_message(initial_prompt)
            self.output_to_screen(f"User prompt: {initial_prompt}", role="user")
            
            # Main interaction loop
            while not self.conversation_ended:
                # Get response from the model
                self.output_to_screen("Generating response...", role="system")
                response = self.get_streaming_response()
                
                # Process the response and execute any tools
                processed_response = self.process_model_response(response)
                
                # Check if the conversation has ended
                if self.conversation_ended:
                    break
                
                # Ask for user input
                self.output_to_screen("Do you want to continue? (Enter your next prompt or type 'exit' to end. Press Enter twice to submit.)", role="system")
                user_input = get_multiline_input("> ")
                
                if user_input.lower() in ["exit", "quit"]:
                    self.output_to_screen("Ending conversation at user request.", role="system")
                    break
                
                # Add user input to the conversation
                self.conversation.add_user_message(user_input)
            
            # Clean up
            self.running = False
            display_thread.join(timeout=1.0)
            
            # Save the conversation
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            self.conversation.save_conversation(f"conversation-{timestamp}.json")
            self.output_to_screen(f"Conversation saved to conversation-{timestamp}.json", role="system")
            
        except KeyboardInterrupt:
            self.output_to_screen("Interrupted by user. Exiting...", role="system")
            self.running = False
        except Exception as e:
            self.output_to_screen(f"Error: {str(e)}\n{traceback.format_exc()}", role="system")
            self.running = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an agent with tool execution capabilities")
    parser.add_argument("--provider", default="openai", help="Model provider (default: openai)")
    parser.add_argument("--model", default="gpt-4", help="Model name (default: gpt-4)")
    parser.add_argument("--prompt", help="Initial prompt for the agent")
    args = parser.parse_args()
    
    runner = AgentRunner(args.provider, args.model)
    
    if args.prompt:
        initial_prompt = args.prompt
    else:
        print("Enter your initial prompt for the agent:")
        initial_prompt = input("> ")
    
    runner.run(initial_prompt) 