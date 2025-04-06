import asyncio
from typing import List, Optional
import os
import importlib
import inspect
from pathlib import Path
from Clients.base import BaseClient, Message, ProviderConfig
from Core.tool_parser import ToolCallParser
from Core.executor import Executor
from Core.stream_manager import StreamManager
from Prompts.main import generate_system_prompt
from Core.utils import get_multiline_input
from Tools.error_codes import ConversationEnded, ErrorCodes

class AgentRunner:

    def __init__(self, provider: str, model: Optional[str] = None, use_system_prompt: bool = True):
        try:
            self.client = self._get_client_instance(provider)
        except ValueError as e:
            print(f"Error initializing client for provider '{provider}': {e}")
            raise
        except Exception as e:
            print(f"Unexpected error initializing client for provider '{provider}': {e}")
            raise

        self.model = model or self.client.config.default_model
        available_models = self.client.get_available_models()
        if self.model not in available_models:
             raise ValueError(f"Model '{self.model}' is not available for provider '{provider}'. Available: {available_models}")

        print(f"AgentRunner initialized with Provider: {provider}, Model: {self.model}")

        self.messages: List[Message] = []
        self.executor = Executor()
        self.tool_parser = ToolCallParser()
        self.stream_manager = StreamManager()

        if use_system_prompt:
            system_prompt = generate_system_prompt(provider)
            self.add_message('system', system_prompt)

    def _get_client_instance(self, provider_name: str) -> BaseClient:
        api_dir = Path(__file__).parent.parent / "Clients" / "API"
        module_path = api_dir / f"{provider_name}.py"
        if not module_path.exists():
            raise ValueError(f"Provider module file not found: {module_path}")

        try:
            module = importlib.import_module(f"Clients.API.{provider_name}")
        except ImportError as e:
            raise ValueError(f"Failed to import provider module 'Clients.API.{provider_name}': {e}")

        client_class = None
        provider_config = None
        config_name = f"{provider_name.upper()}_CONFIG"

        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient:
                 if name.lower() == f"{provider_name}client":
                    client_class = obj
            elif isinstance(obj, ProviderConfig) and name == config_name:
                provider_config = obj

        if not client_class:
             raise ValueError(f"Could not find a client class derived from BaseClient in {module_path}")
        if not provider_config:
             raise ValueError(f"Could not find a ProviderConfig named {config_name} in {module_path}")

        sig = inspect.signature(client_class.__init__)
        try:
            if 'config' in sig.parameters:
                return client_class(config=provider_config)
            else:
                 return client_class()
        except Exception as e:
            raise RuntimeError(f"Failed to instantiate client class '{client_class.__name__}': {e}")


    def add_message(self, role: str, content: str):
         if role not in ["user", "assistant", "system"]:
             print(f"Warning: Invalid message role '{role}'. Using 'user'.")
             role = "user"
         if not isinstance(content, str):
              print(f"Warning: Message content is not a string ({type(content)}). Converting.")
              content = str(content)

         self.messages.append(Message(role=role, content=content))

    async def _run_chat_cycle(self, prompt: str) -> Optional[str]:
        if prompt:
            self.add_message('user', prompt)

        accumulated_response_before_tool = ""
        stream_interrupted_by_tool = False

        try:
            stream = await self.client.chat_completion_stream(
                messages=self.messages,
                model=self.model
            )

            async for chunk in self.stream_manager.process_stream(stream):
                output_text, tool_data = self.tool_parser.feed(chunk)

                if output_text:
                    accumulated_response_before_tool += output_text
                    print(output_text, end='', flush=True)

                if tool_data:
                    print("\n[Tool call detected - interrupting stream]")
                    stream_interrupted_by_tool = True
                    await self.stream_manager.close_stream(stream)
                    # Pass accumulated text before the tool call
                    await self._handle_tool_call(accumulated_response_before_tool, tool_data)
                    print("\n[Continuing after tool execution...]")
                    accumulated_response_before_tool = "" # Reset for recursive call
                    # NOTE: Recursive call might be mocked in tests
                    return await self._run_chat_cycle("")

            if not stream_interrupted_by_tool and accumulated_response_before_tool:
                print()
                self.add_message('assistant', accumulated_response_before_tool)
                return accumulated_response_before_tool

            if not accumulated_response_before_tool.strip() and not stream_interrupted_by_tool:
                 print("\n[Agent produced no text response]")
                 self.add_message('assistant', '')
                 return ""

        except asyncio.TimeoutError:
            print("\n[Streaming timeout]")
            self.add_message('assistant', "[ERROR: Streaming timed out]")
            return "[ERROR: Streaming timed out]"
        except ConversationEnded:
            raise
        except Exception as e:
            error_msg = f"[ERROR: {str(e)}]"
            print(f"\n[Streaming or processing error: {error_msg}]")
            self.add_message('assistant', error_msg)
            return error_msg

        return None


    async def _handle_tool_call(self, partial_response: str, tool_data: dict):
        if partial_response.strip():
            self.add_message('assistant', partial_response.strip())

        tool_name = tool_data.get('tool')
        tool_args_dict = tool_data.get('args', {})
        args_str = "\n".join([f"{k}: {v}" for k, v in tool_args_dict.items()])
        tool_call_string = f"@tool {tool_name}\n{args_str}\n@end"

        tool_result_str = self.executor.execute(tool_call_string)

        print(f"\n[Tool result for {tool_name}]:\n{tool_result_str}\n")
        self.add_message('assistant', tool_result_str)


    async def run(self, initial_prompt: str):
        current_prompt = initial_prompt
        try:
            while True:
                response = await self._run_chat_cycle(current_prompt)
                current_prompt = get_multiline_input("> ")
                if current_prompt is None:
                    print("\nExiting.")
                    break
        except ConversationEnded as e:
             print(f"Agent conversation ended by tool: {e}")
        except KeyboardInterrupt:
            print("\nConversation interrupted by user.")
        except Exception as e:
            print(f"\nAn unexpected error occurred in the main loop: {e}")
            import traceback
            traceback.print_exc()
