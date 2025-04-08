import asyncio
from typing import Dict, List, Optional, TYPE_CHECKING
import traceback

from Clients.base import BaseClient, Message
from Core.tool_parser import ToolCallParser
from Core.executor import Executor
from Core.stream_manager import StreamManager
from Tools.error_codes import ConversationEnded, PauseRequested, ErrorCodes
from Tools.base import Tool, ToolResult
from Prompts.main import build_system_prompt

if TYPE_CHECKING:
    from Core.agent_config import AgentConfiguration

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
        # self.pause_requested_by_tool = False # This flag is no longer needed

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

        if not content.strip() and role != 'system':
            return

        # Prevent adding duplicate "Proceed." messages
        if role == 'user' and content == "Proceed.":
            if self.messages and self.messages[-1].role == 'user' and self.messages[-1].content == "Proceed.":
                return

        self.messages.append(Message(role=role, content=content))

    async def execute_turn(self) -> Optional[str]:
        # self.pause_requested_by_tool = False # Flag removed
        accumulated_response_before_tool = ""
        stream_interrupted_by_tool = False
        stream = None
        final_turn_output = None

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
                    print("\n[Tool call detected - interrupting stream]")
                    stream_interrupted_by_tool = True
                    await self.stream_manager.close_stream(stream)

                    # _handle_tool_call might raise PauseRequested or ConversationEnded
                    await self._handle_tool_call(accumulated_response_before_tool, tool_data)

                    # If _handle_tool_call completed *without* raising an exception
                    # (meaning it was a normal, non-pausing tool)
                    print("[Finishing turn after non-pausing tool execution...]")
                    accumulated_response_before_tool = "" # Reset buffer after successful non-pausing tool
                    return None # Signal orchestrator to potentially continue or add "Proceed."

            # --- Stream finished without interruption ---
            if not stream_interrupted_by_tool:
                if accumulated_response_before_tool:
                    print() # Newline after stream output
                    self.add_message('assistant', accumulated_response_before_tool)
                    final_turn_output = accumulated_response_before_tool
                else:
                    # Handle case where stream completes but outputs nothing
                    final_turn_output = "" 

            return final_turn_output

        except asyncio.TimeoutError:
            print("\n[Streaming timeout]")
            if stream:
                await self.stream_manager.close_stream(stream)
            error_msg = "[ERROR: Streaming timed out]"
            # Don't add error message here, let orchestrator handle based on return
            return error_msg

        # --- Catch exceptions that signal control flow changes ---
        except PauseRequested as pr:
             print(f"[AgentInstance '{self.config.agent_id}' propagating PauseRequested]")
             raise pr # Propagate upwards
        except ConversationEnded as ce:
            print(f"\n[AgentInstance '{self.config.agent_id}' propagating ConversationEnded]")
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

            # Return error message for Orchestrator to handle
            return error_msg

        # Fallback if somehow execution reaches here unexpectedly
        # return "[ERROR: Unexpected end of execute_turn]"
        # If no tool was called and stream ended, final_turn_output holds the text or ""
        return final_turn_output


    async def _handle_tool_call(self, partial_response: str, tool_data: dict):
        # Add any text accumulated before the tool call
        if partial_response.strip():
            self.add_message('assistant', partial_response.strip())

        tool_name = tool_data.get('tool')
        tool_args_dict = tool_data.get('args', {})
        result_str = ""
        tool_succeeded = False
        parsed_exit_code = ErrorCodes.UNKNOWN_ERROR

        # Check permissions
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
            print(f"\n[Agent '{self.config.agent_id}' DENIED permission for tool: {tool_name}]")
            result_str = format_result(tool_name, ErrorCodes.PERMISSION_DENIED, "Agent does not have permission to use this tool.")
            parsed_exit_code = ErrorCodes.PERMISSION_DENIED
            self.add_message('assistant', f"Tool {tool_name} permission denied.") # Add denial message
        else:
            # Format and add the *intention* to call the tool
            args_str = "\n".join([f"{k}: {v}" for k, v in tool_args_dict.items()])
            tool_call_intention_content = f"Calling tool: {tool_name} with arguments:\n{args_str}"
            # Don't add this to history, LLM already generated the @tool block
            # self.add_message('assistant', tool_call_intention_content) 

            tool_executor_input = f"@tool {tool_name}\n{args_str}\n@end"
            print(f"\n[Agent '{self.config.agent_id}' executing tool: {tool_name}]")

            try:
                # Execute the tool
                # This might raise ConversationEnded if the tool is 'end'
                result_str = self.executor.execute(tool_executor_input, agent_config=self.config)
                print(f"\n[Tool result for {tool_name}]:\n{result_str}\n")

                # Parse exit code from the result string
                if result_str.startswith(f"@result {tool_name}"):
                    lines = result_str.split('\n')
                    for line in lines:
                        if line.startswith("exit_code: "):
                            try:
                                parsed_exit_code = int(line.split("exit_code: ", 1)[1])
                                tool_succeeded = (parsed_exit_code == ErrorCodes.SUCCESS)
                                break
                            except (ValueError, IndexError):
                                print(f"Warning: Could not parse exit code from tool result for {tool_name}")

            except ConversationEnded as ce:
                # Re-raise ConversationEnded to be caught by execute_turn/orchestrator
                 print(f"[AgentInstance caught ConversationEnded from tool '{tool_name}', re-raising]")
                 raise ce

            except Exception as exec_err:
                print(f"ERROR during executor.execute for tool {tool_name}: {exec_err}")
                traceback.print_exc()
                result_str = format_result(tool_name, ErrorCodes.UNKNOWN_ERROR, f"Executor error: {exec_err}")
                parsed_exit_code = ErrorCodes.UNKNOWN_ERROR

        # --- Add the actual tool result to message history ---
        # Do this *before* raising PauseRequested
        self.add_message('assistant', f"Tool {tool_name} execution result:\n{result_str}")

        # --- Check for Pause condition ---
        if tool_name == "pause" and tool_succeeded:
            # Extract the specific output message from the tool result string
            pause_message = "Agent paused. Please provide input or press Enter to continue." # Default
            try:
                lines = result_str.split('\n')
                for line in lines:
                    if line.startswith("output: "):
                        # Decode potential @_end safety mechanism
                        pause_message = line.split("output: ", 1)[1].strip().replace('@_end', '@end') 
                        break
            except Exception as parse_err:
                 print(f"Warning: Error parsing pause message from result string: {parse_err}")

            # Raise the specific exception for the orchestrator
            print(f"[AgentInstance raising PauseRequested for tool '{tool_name}']")
            raise PauseRequested(pause_message)

        # If it wasn't a successful pause, the method ends here,
        # and execute_turn will return None (signalling tool completed normally).
