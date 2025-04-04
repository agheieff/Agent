import asyncio
from typing import List, Optional
from Clients import BaseClient, Message
from Clients.base import Message
from Core.tool_parser import ToolCallParser
from Core.executor import Executor
from Core.stream_manager import StreamManager

class AgentRunner:
    def __init__(self, provider: str, model: str = None, use_system_prompt: bool = True):
        self.client = self._init_client(provider)
        self.model = model or self.client.config.default_model
        self.messages: List[Message] = []
        self.executor = Executor()
        self.stream_manager = StreamManager()
        self.tool_parser = ToolCallParser()

        if use_system_prompt:
            system_prompt = generate_system_prompt(provider)
            self.add_message('system', system_prompt)

    def _init_client(self, provider: str) -> BaseClient:
        try:
            module = __import__(f'Clients.API.{provider.lower()}', fromlist=['*'])
            for name, obj in module.__dict__.items():
                if name.endswith('Client') and name.lower().startswith(provider.lower()):
                    return obj()
            for name, obj in module.__dict__.items():
                if name.endswith('Client'):
                    return obj()
            raise ValueError(f"No client class found in module Clients.API.{provider}")
        except ImportError as e:
            raise ImportError(f"Provider module not found: {provider}") from e
        except Exception as e:
            raise RuntimeError(f"Error initializing client for {provider}: {str(e)}") from e

    def add_message(self, role: str, content: str):
        self.messages.append(Message(role=role, content=content))

    async def _run_chat_cycle(self, prompt: str) -> str:
        """Enhanced streaming with tool interruption"""
        self.add_message('user', prompt)
        full_response = ""

        try:
            stream = self.client.chat_completion_stream(
                messages=self.messages,
                model=self.model
            )

            async for chunk in self.stream_manager.process_stream(stream):
                text, tool_call = self.tool_parser.feed(chunk)

                if text:
                    full_response += text
                    print(text, end='', flush=True)

                if tool_call:
                    print("\n[Tool detected - interrupting stream]")
                    await self.stream_manager.close_stream(stream)
                    return await self._handle_tool_call(full_response, tool_call)

            if full_response:
                self.add_message('assistant', full_response)
            return full_response

        except asyncio.TimeoutError:
            print("\n[Streaming timeout]")
            return "[ERROR: Streaming timed out]"
        except Exception as e:
            print(f"\n[Streaming error: {str(e)}]")
            return f"[ERROR: {str(e)}]"

    async def _handle_tool_call(self, partial_response: str, tool_data: dict) -> str:
        """Handle tool execution and continuation"""
        if partial_response.strip():
            self.add_message('assistant', partial_response)

        # Format tool call into a message and add it to the conversation
        tool_call_string = f"@tool {tool_data.get('name')}\n{tool_data.get('args', '')}\n@end"
        self.add_message('assistant', tool_call_string)
        
        # Execute tool
        tool_result = self.executor.execute(tool_data)
        print(f"\n[Tool result]: {tool_result}\n")

        # Add tool result to the conversation
        self.add_message('assistant', tool_result)
        
        # Continue the conversation
        self.add_message('user', "")
        return await self._run_chat_cycle("")
