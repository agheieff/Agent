import asyncio
from typing import List, Optional
from Clients import BaseClient, Message
from Clients.base import Message
from Core.tool_parser import ToolCallParser
from Core.executor import Executor
from Core.stream_manager import StreamManager
from Prompts.main import generate_system_prompt
from Core.utils import get_multiline_input
from Tools.error_codes import ConversationEnded

class AgentRunner:

    async def _run_chat_cycle(self, prompt: str) -> Optional[str]:
        if prompt:
             self.add_message('user', prompt)
        full_response = ""
        stream_interrupted_by_tool = False

        try:
            stream = self.client.chat_completion_stream(
                messages=self.messages,
                model=self.model
            )

            async for chunk in self.stream_manager.process_stream(stream):
                text, tool_data = self.tool_parser.feed(chunk)

                if text:
                    full_response += text
                    print(text, end='', flush=True)

                if tool_data:
                    print("\n[Tool call detected - interrupting stream]")
                    stream_interrupted_by_tool = True
                    await self.stream_manager.close_stream(stream)
                    await self._handle_tool_call(full_response, tool_data)
                    print("\n[Continuing after tool execution...]")
                    return await self._run_chat_cycle("")

            if not stream_interrupted_by_tool and full_response:
                print()
                self.add_message('assistant', full_response)
                return full_response

            if not full_response.strip() and not stream_interrupted_by_tool:
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

        if full_response and not stream_interrupted_by_tool:
             print()
             self.add_message('assistant', full_response)
             return full_response
        return None

    async def _handle_tool_call(self, partial_response: str, tool_data: dict):
        if partial_response.strip():
            self.add_message('assistant', partial_response.strip())

        tool_name = tool_data.get('tool')
        tool_args_dict = tool_data.get('args', {})
        args_str = "\n".join([f"{k}: {v}" for k, v in tool_args_dict.items()])
        tool_call_string = f"@tool {tool_name}\n{args_str}\n@end"
        self.add_message('assistant', tool_call_string)

        tool_result_str = self.executor.execute(tool_call_string)

        print(f"\n[Tool result]:\n{tool_result_str}\n")

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
        except ConversationEnded:
            print("Agent conversation ended.")
        except KeyboardInterrupt:
             print("\nConversation interrupted by user.")
        except Exception as e:
             print(f"\nAn unexpected error occurred in the main loop: {e}")
