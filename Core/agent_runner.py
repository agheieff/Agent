import asyncio
from dataclasses import dataclass
from typing import List

from Clients import BaseClient, Message
from Core.utils import get_multiline_input
from Core.executor import parse_tool_call, Executor, format_result
from Prompts.main import generate_system_prompt

@dataclass
class AgentMessage:
    role: str
    content: str

class AgentRunner:
    def __init__(self, provider: str, model: str = None, use_system_prompt: bool = True):
        self.client = self._init_client(provider)
        self.model = model or self.client.config.default_model
        self.messages: List[AgentMessage] = []
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
        self.messages.append(AgentMessage(role, content))

    async def _run_chat_cycle(self, prompt: str):
        self.add_message('user', prompt)

        client_messages = [
            Message(role=msg.role, content=msg.content)
            for msg in self.messages
        ]

        response_text = await self.client.chat_completion(
            messages=client_messages,
            model=self.model
        )

        while True:
            try:
                _ = parse_tool_call(response_text)
                tool_result_str = self.executor.execute(response_text)
                self.add_message('assistant', tool_result_str)
                if "CONVERSATION_END" in tool_result_str:
                    return "[Conversation ended by tool]"
                break
            except ValueError:
                break

        self.add_message('assistant', response_text)
        return response_text

    def run(self, prompt: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            initial_response = loop.run_until_complete(self._run_chat_cycle(prompt))
            print(f"\nAssistant: {initial_response}")

            while True:
                try:
                    follow_up = get_multiline_input("\nYou: ")
                    if not follow_up.strip():
                        continue
                    response = loop.run_until_complete(self._run_chat_cycle(follow_up))
                    print(f"\nAssistant: {response}")
                    if any(end_word in response.lower() for end_word in ['goodbye', 'farewell', 'exit']):
                        break
                except EOFError:
                    break
        except KeyboardInterrupt:
            print("\nSession ended by user")
        finally:
            loop.close()
