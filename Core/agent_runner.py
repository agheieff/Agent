import asyncio
from typing import List, Optional, TYPE_CHECKING
import traceback

from Clients.base import BaseClient, Message
from Core.tool_parser import ToolCallParser
from Core.executor import Executor
from Core.stream_manager import StreamManager
from Tools.error_codes import ConversationEnded, ErrorCodes

if TYPE_CHECKING:
    from Core.agent_config import AgentConfiguration

class AgentInstance:
    def __init__(self, config: 'AgentConfiguration', client: BaseClient, executor: Executor):
        if not config or not client or not executor:
             raise ValueError("AgentInstance requires config, client, and executor.")

        self.config = config
        self.client = client
        self.executor = executor

        self.messages: List[Message] = []
        self.tool_parser = ToolCallParser()
        self.stream_manager = StreamManager()

        print(f"AgentInstance '{self.config.agent_id}' ({self.config.role}) initialized.")
        print(f"  Model: {self.config.model_provider}/{self.config.model_name}")
        print(f"  Allowed Tools: {self.config.allowed_tools or 'All'}")

        if self.config.system_prompt:
            self.add_message('system', self.config.system_prompt)

    def add_message(self, role: str, content: str):
        if role not in ["user", "assistant", "system"]:
            print(f"Warning (Agent: {self.config.agent_id}): Invalid message role '{role}'. Using 'user'.")
            role = "user"
        if not isinstance(content, str):
            content = str(content)
        if not content.strip() and role != 'system':
             print(f"Warning (Agent: {self.config.agent_id}): Attempted to add empty message for role '{role}'. Skipping.")
             return

        if role == 'user' and content == "Proceed.":
             if self.messages and self.messages[-1].role == 'user' and self.messages[-1].content == "Proceed.":
                  return

        self.messages.append(Message(role=role, content=content))

    async def execute_turn(self) -> Optional[str]:
        accumulated_response_before_tool = ""
        stream_interrupted_by_tool = False
        stream = None
        final_turn_output = None

        try:
            if not self.messages or self.messages[-1].role == 'system':
                 print(f"Warning (Agent: {self.config.agent_id}): Cannot execute turn starting with system prompt. Add user message.")
                 # Or add a default user message? self.add_message('user', '...')
                 return "[ERROR: Turn cannot start with system message]"

            # --- Get stream from LLM ---
            # Note: Removed 'await' based on previous debugging for Anthropic client
            stream = self.client.chat_completion_stream(
                messages=self.messages,
                model=self.config.model_name # Use model from config
            )

            processed_stream_generator = self.stream_manager.process_stream(stream)

            # --- Process Stream ---
            async for chunk in processed_stream_generator:
                output_text, tool_data = self.tool_parser.feed(chunk)

                if output_text:
                    accumulated_response_before_tool += output_text
                    print(output_text, end='', flush=True)

                if tool_data:
                    print("\n[Tool call detected - interrupting stream]")
                    stream_interrupted_by_tool = True
                    await self.stream_manager.close_stream(stream)
                    # Handle tool call internally, updating self.messages
                    await self._handle_tool_call(accumulated_response_before_tool, tool_data)
                    print("[Continuing after tool execution...]")
                    accumulated_response_before_tool = ""
                    return None

            if not stream_interrupted_by_tool:
                if accumulated_response_before_tool:
                    print()
                    self.add_message('assistant', accumulated_response_before_tool)
                    final_turn_output = accumulated_response_before_tool
                else:
                    print("\n[Agent produced no text response for this turn segment]")
                    final_turn_output = ""

            return final_turn_output

        except asyncio.TimeoutError:
            print("\n[Streaming timeout]")
            if stream: await self.stream_manager.close_stream(stream)
            error_msg = "[ERROR: Streaming timed out]"
            self.add_message('assistant', error_msg)
            return error_msg
        except ConversationEnded as ce:
             print(f"\n[ConversationEnded signal received by agent '{self.config.agent_id}']")
             raise ce
        except Exception as e:
            error_msg = f"[ERROR: {type(e).__name__} - {str(e)}]"
            print(f"\n[Agent '{self.config.agent_id}' processing error: {error_msg}]")
            traceback.print_exc()
            if stream:
                try: await self.stream_manager.close_stream(stream)
                except Exception as close_err: print(f"[Error closing stream after exception: {close_err}]")
            self.add_message('assistant', error_msg)
            return error_msg

        return "[ERROR: Unexpected end of execute_turn]"

    async def _handle_tool_call(self, partial_response: str, tool_data: dict):
        if partial_response.strip():
            self.add_message('assistant', partial_response.strip())

        tool_name = tool_data.get('tool')
        tool_args_dict = tool_data.get('args', {})

        # --- Permission Check ---
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
             print(f"\n[Agent '{self.config.agent_id}' DENIED permission for tool: {tool_name}]")
             result_str = f"@result {tool_name}\nexit_code: {ErrorCodes.PERMISSION_DENIED}\noutput: Agent does not have permission to use this tool.\n@end"
        else:
            # --- Execute Tool ---
            args_str = "\n".join([f"{k}: {v}" for k, v in tool_args_dict.items()])
            # Log the planned tool call
            tool_call_message_content = f"Calling tool: {tool_name} with arguments:\n{args_str}"
            self.add_message('assistant', tool_call_message_content)

            tool_executor_input = f"@tool {tool_name}\n{args_str}\n@end"
            print(f"\n[Agent '{self.config.agent_id}' executing tool: {tool_name}]")
            result_str = self.executor.execute(tool_executor_input) # Use shared executor
            print(f"\n[Tool result for {tool_name}]:\n{result_str}\n")

            # --- Handle Pause Tool Side-Effect ---
            # The 'pause' tool itself still handles the input() call.
            # The Orchestrator will need to know if pause was called to halt the main loop.
            # This instance doesn't know about the external loop, so we just note it happened.
            if tool_name == "pause":
                 print(f"[Agent '{self.config.agent_id}' used Pause Tool]")
                 # We need a way to signal this back to the orchestrator.
                 # For now, the orchestrator won't know. We'll add this later.

        self.add_message('assistant', f"Tool {tool_name} execution result:\n{result_str}")
