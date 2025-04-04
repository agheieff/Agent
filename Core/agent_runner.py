import asyncio
from typing import List

from Clients import BaseClient, Message
from Core.utils import get_multiline_input
from Core.executor import parse_tool_call, Executor, format_result
from Prompts.main import generate_system_prompt

class AgentRunner:
    def __init__(self, provider: str, model: str = None, use_system_prompt: bool = True):
        self.client = self._init_client(provider)
        self.model = model or self.client.config.default_model
        self.messages: List[Message] = []
        self.executor = Executor()
        self.provider_name = provider

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

    async def _run_chat_cycle(self, prompt: str):
        self.add_message('user', prompt)
        parser = ToolCallParser()
        full_response = ""
        tool_called = False

        async for chunk in self.client.chat_completion_stream(
            messages=self.messages,
            model=self.model
        ):
            text, tool_call = parser.feed(chunk)

            if text:
                full_response += text
                print(text, end='', flush=True)

            if tool_call:
                tool_called = True
                print()  # New line after tool call
                break  # Stop streaming immediately when tool call is found

        if tool_called:
            tool_result = self.executor.execute(full_response)
            print(f"\nTool result: {tool_result}\n")

            if full_response.strip():
                self.add_message('assistant', full_response)

            self.add_message('user', tool_result)
            return await self._run_chat_cycle("")

        self.add_message('assistant', full_response)
        return full_response
