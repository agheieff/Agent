import asyncio
from dataclasses import dataclass
from typing import List

from Clients import BaseClient, Message
from Core.utils import get_multiline_input
from Core.executor import parse_tool_call, Executor, format_result
from Prompts.main import generate_system_prompt

@dataclass
class AgentMessage:
    role: str  # 'user', 'assistant', 'system'
    content: str

class AgentRunner:
    def __init__(self, provider: str, model: str = None, use_system_prompt: bool = True):
        self.client = self._init_client(provider)
        self.model = model or self.client.config.default_model
        self.messages: List[AgentMessage] = []
        self.executor = Executor()  # For executing tool calls
        self.provider_name = provider
        
        # Optionally load a system prompt with tool documentation.
        if use_system_prompt:
            system_prompt = generate_system_prompt(provider)
            self.add_message('system', system_prompt)

    def _init_client(self, provider: str) -> BaseClient:
        """Initialize the appropriate client based on provider name."""
        try:
            module = __import__(f'Clients.API.{provider.lower()}', fromlist=['*'])
            # Look for classes that end with 'Client' and match the provider.
            for name, obj in module.__dict__.items():
                if name.endswith('Client') and name.lower().startswith(provider.lower()):
                    return obj()
            # Fallback: return any Client class found.
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
        """
        1) Add a user message.
        2) Request a response from the LLM.
        3) Parse the response for a tool call.
        4) If a tool call is detected, execute the tool and record its result.
        """
        # Step 1: Add the user's message.
        self.add_message('user', prompt)
        
        # Convert conversation to the client message format.
        client_messages = [
            Message(role=msg.role, content=msg.content)
            for msg in self.messages
        ]
        
        # Step 2: Get the LLM's response.
        response_text = await self.client.chat_completion(
            messages=client_messages,
            model=self.model
        )
        
        # Step 3: Check for a tool call in the response.
        while True:
            try:
                # Try to parse a tool call.
                _ = parse_tool_call(response_text)
                # If parsing succeeds, execute the tool.
                tool_result_str = self.executor.execute(response_text)
                # Add the tool execution result as an assistant message.
                self.add_message('assistant', tool_result_str)
                # If the tool signals an end, break the cycle.
                if "CONVERSATION_END" in tool_result_str:
                    return "[Conversation ended by tool]"
                # Exit the loop after handling a tool call.
                break
            except ValueError:
                # No valid tool call found; break out.
                break

        # Step 4: Add the LLM response as an assistant message.
        self.add_message('assistant', response_text)
        return response_text

    def run(self, prompt: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            initial_response = loop.run_until_complete(self._run_chat_cycle(prompt))
            print(f"\nAssistant: {initial_response}")
            
            # Continue with interactive follow-up prompts.
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
