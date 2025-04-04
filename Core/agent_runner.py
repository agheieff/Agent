import asyncio
from typing import List, Optional
from Clients import BaseClient, Message
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

    async def _run_chat_cycle(self, prompt: str) -> str:
        """Enhanced streaming with tool interruption"""
        self.add_message('user', prompt)
        full_response = ""

        try:
            stream = self.client.chat_completion_stream(
                messages=self.messages,
                model=self.model
            )

            async for chunk in await self.stream_manager.process_stream(stream):
                text, tool_call = self.tool_parser.feed(chunk)

                if text:
                    full_response += text
                    print(text, end='', flush=True)

                if tool_call:
                    print("\n[Tool detected - interrupting stream]")
                    await self.stream_manager.close_stream(stream)
                    return await self._handle_tool_call(full_response, tool_call)

        except asyncio.TimeoutError:
            print("\n[Streaming timeout]")
            return "[ERROR: Streaming timed out]"
        except Exception as e:
            print(f"\n[Streaming error: {str(e)}]")
            return f"[ERROR: {str(e)}]"

        self.add_message('assistant', full_response)
        return full_response

    async def _handle_tool_call(self, partial_response: str, tool_data: dict) -> str:
        """Handle tool execution and continuation"""
        if partial_response.strip():
            self.add_message('assistant', partial_response)

        # Execute tool
        tool_result = self.executor.execute(tool_data)
        print(f"\n[Tool result]: {tool_result}\n")

        self.add_message('user', tool_result)
        return await self._run_chat_cycle("")
