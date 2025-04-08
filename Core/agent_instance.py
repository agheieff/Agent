import asyncio
from typing import Dict, List, Optional, TYPE_CHECKING, Union
import traceback
import re # Import re for parsing

from Clients.base import BaseClient, Message
from Core.tool_parser import ToolCallParser
from Core.executor import Executor
from Core.stream_manager import StreamManager
from Tools.error_codes import ConversationEnded, PauseRequested, ErrorCodes
from Tools.base import Tool, ToolResult
from Prompts.main import build_system_prompt

if TYPE_CHECKING:
    from Core.agent_config import AgentConfiguration

# Define a unique signal object
TOOL_EXECUTED_SIGNAL = object()

def format_result(name: str, exit_code: int, output: str) -> str:
    safe_output = str(output).replace('@end', '@_end')
    return f"@result {name}\nexit_code: {exit_code}\noutput: {safe_output}\n@end"

class AgentInstance:
    def __init__(self, config: 'AgentConfiguration', client: BaseClient, executor: Executor, all_discovered_tools: Dict[str, Tool]):
        if not config or not client or not executor or all_discovered_tools is None:
            raise ValueError("AgentInstance requires config, client, executor, and all_discovered_tools.")

        self.config = config
        self.client = client
        self.executor = executor
        self.all_discovered_tools = all_discovered_tools
        self.messages: List[Message] = []
        self.tool_parser = ToolCallParser()
        self.stream_manager = StreamManager()

        system_prompt_text = build_system_prompt(self.config, self.all_discovered_tools)
        if system_prompt_text:
            self.add_message('system', system_prompt_text)
        else:
            print(f"Warning (Agent: {self.config.agent_id}): Generated system prompt is empty.")

        print(f"AgentInstance '{self.config.agent_id}' ({self.config.role}) initialized.")
        print(f"  Model: {self.config.model_provider}/{self.config.model_name}")
        print(f"  Allowed Tools: {self.config.allowed_tools or 'None'}")

    def add_message(self, role: str, content: str):
        if role not in ["user", "assistant", "system"]:
            print(f"Warning (Agent: {self.config.agent_id}): Invalid message role '{role}'. Using 'user'.")
            role = "user"

        if not isinstance(content, str):
            content = str(content)

        # Allow empty system messages, but generally avoid empty user/assistant messages
        # Allow empty assistant messages only if they follow a raw tool result message
        if not content.strip() and role != 'system':
             if not (self.messages and self.messages[-1].role == 'assistant' and self.messages[-1].content.startswith("[Tool Result for")):
                  return


        # Prevent adding duplicate "Proceed." messages
        if role == 'user' and content == "Proceed.":
            if self.messages and self.messages[-1].role == 'user' and self.messages[-1].content == "Proceed.":
                return

        self.messages.append(Message(role=role, content=content))

    async def execute_turn(self) -> Union[Optional[str], object]: # Updated return type hint
        accumulated_response_before_tool = ""
        stream_interrupted_by_tool = False
        stream = None
        final_turn_output = None
        tool_call_occurred = False # Add a flag to track if any tool was called this turn

        try:
            if not self.messages:
                return "[ERROR: Turn cannot start with empty history]"

            if len(self.messages) == 1 and self.messages[0].role == 'system':
                return "[ERROR: Turn cannot start with only a system message]"

            stream = self.client.chat_completion_stream(
                messages=self.messages,
                model=self.config.model_name
            )

            processed_stream_generator = self.stream_manager.process_stream(stream)

            async for chunk in processed_stream_generator:
                output_text, tool_data = self.tool_parser.feed(chunk)

                if output_text:
                    accumulated_response_before_tool += output_text
                    print(output_text, end='', flush=True)

                if tool_data:
                    tool_call_occurred = True # Mark that a tool was called
                    print("\n[Tool call detected - interrupting stream]")
                    stream_interrupted_by_tool = True
                    # Ensure stream is closed *before* handling the tool call
                    if stream:
                         await self.stream_manager.close_stream(stream)
                         stream = None # Avoid trying to close again later

                    # _handle_tool_call might raise PauseRequested or ConversationEnded
                    # It now adds the RAW tool result to history itself.
                    await self._handle_tool_call(accumulated_response_before_tool, tool_data)

                    # If _handle_tool_call completed *without* raising an exception
                    # (meaning it was a normal, non-pausing tool)
                    print("[Finishing turn after non-pausing tool execution...]")
                    # _handle_tool_call added raw result to history
                    # Pre-tool text is NO LONGER added by _handle_tool_call
                    return TOOL_EXECUTED_SIGNAL # Return signal

            # --- Stream finished without interruption ---
            if not stream_interrupted_by_tool:
                if accumulated_response_before_tool:
                    print() # Newline after stream output
                    self.add_message('assistant', accumulated_response_before_tool)
                    final_turn_output = accumulated_response_before_tool
                # Check if stream ended AND no tool was ever triggered this turn
                elif not tool_call_occurred:
                     # Handle case where stream completes but outputs nothing AND no tool was called
                     final_turn_output = ""
                     self.add_message('assistant', final_turn_output) # Add empty message
                else: # Stream ended, no final text, but a tool was called earlier
                    final_turn_output = "" # Return empty, history already updated by _handle_tool_call

            # Return the final text output (could be empty)
            return final_turn_output


        except asyncio.TimeoutError:
            print("\n[Streaming timeout]")
            if stream:
                await self.stream_manager.close_stream(stream)
            error_msg = "[ERROR: Streaming timed out]"
            return error_msg

        # --- Catch exceptions that signal control flow changes ---
        except PauseRequested as pr:
            print(f"[AgentInstance '{self.config.agent_id}' propagating PauseRequested]")
            if stream: await self.stream_manager.close_stream(stream) # Ensure stream closed on pause
            raise pr # Propagate upwards
        except ConversationEnded as ce:
            print(f"\n[AgentInstance '{self.config.agent_id}' propagating ConversationEnded]")
            if stream: await self.stream_manager.close_stream(stream) # Ensure stream closed on end
            raise ce # Propagate upwards

        # --- Catch other exceptions ---
        except Exception as e:
            if isinstance(e, TypeError) and "async_generator" in str(e) and "await" in str(e):
                error_msg = "[ERROR: Client stream method returned generator directly - code needs adjustment]"
                print(f"\n[Agent '{self.config.agent_id}' FATAL error: {error_msg}] - {e}")
            else:
                error_msg = f"[ERROR: {type(e).__name__} - {str(e)}]"
                print(f"\n[Agent '{self.config.agent_id}' processing error: {error_msg}]")
                traceback.print_exc()

            if stream:
                try:
                    await self.stream_manager.close_stream(stream)
                except Exception as close_err:
                    print(f"[Error closing stream after exception: {close_err}]")

            return error_msg

        # Fallback return
        return final_turn_output


    async def _handle_tool_call(self, partial_response: str, tool_data: dict):
        # --- Pre-tool text is NOT added to history in this version ---
        # if partial_response and partial_response.strip():
        #    self.add_message('assistant', partial_response.strip())


        tool_name = tool_data.get('tool')
        tool_args_dict = tool_data.get('args', {})
        result_str = "" # Will hold the raw @result string from executor
        tool_succeeded = False
        parsed_exit_code = ErrorCodes.UNKNOWN_ERROR
        tool_output_message_for_pause = "" # Specific variable for pause message parsing

        # Check permissions
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
            print(f"\n[Agent '{self.config.agent_id}' DENIED permission for tool: {tool_name}]")
            self.add_message('assistant', f"Permission denied for tool: {tool_name}.")
            return

        # --- If permission granted, execute the tool ---
        else:
            args_str = "\n".join([f"{k}: {v}" for k, v in tool_args_dict.items()])
            tool_executor_input = f"@tool {tool_name}\n{args_str}\n@end"
            print(f"\n[Agent '{self.config.agent_id}' executing tool: {tool_name}]")

            try:
                # Execute the tool - might raise ConversationEnded
                result_str = self.executor.execute(tool_executor_input, agent_config=self.config)
                print(f"\n[Tool result raw string for {tool_name}]:\n{result_str}\n") # Log raw result

                # --- Parse exit code and output message *only needed for pause check* ---
                # Minimal parsing just to determine success and get pause message
                if result_str.startswith(f"@result {tool_name}"):
                    lines = result_str.split('\n')
                    output_lines = []
                    in_output_section = False
                    for line in lines:
                        if line.startswith("exit_code: "):
                            try:
                                parsed_exit_code = int(line.split("exit_code: ", 1)[1])
                                tool_succeeded = (parsed_exit_code == ErrorCodes.SUCCESS)
                            except (ValueError, IndexError):
                                tool_succeeded = False # Treat parse error as failure
                        elif line.startswith("output:"):
                            output_lines.append(line.split("output: ", 1)[1])
                            in_output_section = True
                        elif in_output_section and line.strip() == "@end":
                            in_output_section = False
                        elif in_output_section:
                            output_lines.append(line)

                    if output_lines:
                        tool_output_message_for_pause = "\n".join(output_lines).replace('@_end', '@end').strip()

                else: # Raw result string didn't start with expected format
                     tool_succeeded = False # Assume failure if format is wrong

            except ConversationEnded as ce:
                print(f"[AgentInstance caught ConversationEnded from tool '{tool_name}', re-raising]")
                raise ce
            except Exception as exec_err:
                print(f"ERROR during executor.execute for tool {tool_name}: {exec_err}")
                traceback.print_exc()
                # Format an error result string if execution failed badly
                result_str = format_result(tool_name, ErrorCodes.UNKNOWN_ERROR, f"Executor error: {exec_err}")
                tool_succeeded = False # Ensure failure flag is set

            # --- REVERTED: Add the FULL raw tool result string to message history ---
            history_message = f"[Tool Result for {tool_name}]:\n{result_str}" # Use the raw result_str
            self.add_message('assistant', history_message)
            print(f"[Added to History]: {history_message}") # Log what was added


        # --- Check for Pause condition (using the parsed message) ---
        if tool_name == "pause" and tool_succeeded:
            pause_display_message = tool_output_message_for_pause if tool_output_message_for_pause else \
                                    "Agent paused. Please provide input or press Enter to continue."
            print(f"[AgentInstance raising PauseRequested for tool '{tool_name}' with message: '{pause_display_message}']")
            raise PauseRequested(pause_display_message)

        # If it wasn't a successful pause or end (which raises), the method ends here,
        # and execute_turn will return TOOL_EXECUTED_SIGNAL.
