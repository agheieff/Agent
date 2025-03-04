import sys
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class OutputManager:
    def __init__(self):
        self.tool_formatters = {}
        self._register_default_formatters()

    def _register_default_formatters(self):
        self.register_formatter("default", self._default_formatter)
        self.register_formatter("error", self._error_formatter)
        self.register_formatter("command", self._command_formatter)
        self.register_formatter("file_content", self._file_content_formatter)
        self.register_formatter("file_operation", self._file_operation_formatter)
        self.register_formatter("http_request", self._http_request_formatter)
        self.register_formatter("telegram", self._telegram_formatter)
        self.register_formatter("telegram_messages", self._telegram_messages_formatter)
        self.register_formatter("status", self._status_formatter)
        self.register_formatter("user_interaction", self._user_interaction_formatter)
        self.register_formatter("agent_message", self._agent_message_formatter)
        self.register_formatter("conversation_end", self._conversation_end_formatter)
        self.register_formatter("api_usage", self._api_usage_formatter)
        self.register_formatter("api_usage_summary", self._api_usage_summary_formatter)

    def register_formatter(self, formatter_name: str, formatter_func):
        self.tool_formatters[formatter_name] = formatter_func

    async def handle_tool_output(self, tool_name: str, output: Dict[str, Any]) -> str:
        formatter_name = output.get("formatter", tool_name)
        formatter = self.tool_formatters.get(formatter_name, self.tool_formatters["default"])

        formatted_output = await formatter(output)

        self.display_output(formatted_output)

        return formatted_output

    async def handle_tool_outputs(self, tool_outputs: List[Tuple[str, Dict[str, Any]]]) -> List[str]:
        formatted_outputs = []

        for tool_name, output in tool_outputs:
            formatted_output = await self.handle_tool_output(tool_name, output)
            formatted_outputs.append(formatted_output)

        return formatted_outputs

    def display_output(self, output: str):
        print(output)
        sys.stdout.flush()

    async def get_user_input(self, prompt: str = "> ") -> str:
        print(prompt, end="", flush=True)

        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, sys.stdin.readline)

        return user_input.rstrip("\n")

    async def get_user_confirmation(self, prompt: str = "Confirm? [y/N]: ") -> bool:
        response = await self.get_user_input(prompt)
        return response.lower() in ["y", "yes"]


    async def _default_formatter(self, output: Dict[str, Any]) -> str:
        if isinstance(output, dict):
            if "error" in output and output["error"]:
                return f"Error: {output['error']}"
            elif "output" in output:
                return str(output["output"])
            else:
                return str(output)
        else:
            return str(output)

    async def _error_formatter(self, output: Dict[str, Any]) -> str:
        error_msg = output.get("error", "Unknown error")
        return f"Error: {error_msg}"

    async def _command_formatter(self, output: Dict[str, Any]) -> str:
        cmd_output = output.get("output", "")
        exit_code = output.get("exit_code", 0)
        command = output.get("command", "")

        if exit_code != 0:
            error = output.get("error", "")
            return f"Command failed (exit code {exit_code}):\n$ {command}\n{error}\n{cmd_output}"
        else:
            return f"$ {command}\n{cmd_output}"

    async def _file_content_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'Unknown error')}"

        if output.get("binary", False):
            return f"[Binary file: {output.get('file_path', 'unknown')}]"

        file_path = output.get("file_path", "")
        truncated = output.get("truncated", False)
        line_count = output.get("line_count", 0)
        offset = output.get("offset", 0)

        info = f"File: {file_path}\nLines {offset+1}-{offset+line_count}"
        if truncated:
            info += " (truncated)"

        return f"{info}\n---\n{output.get('content', '')}"

    async def _file_operation_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            file_path = output.get("file_path", "unknown")
            return f"Error: {output.get('error', f'File operation failed on {file_path}')}"

        action = output.get("action", "")
        file_path = output.get("file_path", "")

        if action == "create" or output.get("created", False):
            file_size = output.get("file_size", 0)
            return f"Created file: {file_path} ({file_size} bytes)"

        elif action == "edit" or output.get("edited", False):
            return f"Edited file: {file_path}"

        else:
            return output.get("output", f"File operation completed on {file_path}")

    async def _http_request_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'HTTP request failed')}"

        method = output.get("method", "GET")
        url = output.get("url", "")
        status_code = output.get("status_code", 0)

        formatted = f"{method} {url} - Status: {status_code}\n\n"
        if status_code >= 400:
            formatted += "Error Response:\n"
        formatted += output.get("response_body", "")

        return formatted

    async def _telegram_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'Telegram API error')}"

        message = output.get("message", "")
        chat_id = output.get("chat_id", "")
        sent = output.get("sent", False)

        if sent:
            return f"Message sent to Telegram chat {chat_id}:\n{message}"
        else:
            return output.get("output", "Unknown status")

    async def _telegram_messages_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'Telegram API error')}"

        messages = output.get("messages", [])
        if not messages:
            return "No Telegram messages available"

        formatted = "Recent Telegram messages:\n\n"
        for msg in messages:
            formatted += f"From: {msg.get('sender', 'Unknown')}\n"
            formatted += f"Message: {msg.get('text', '')}\n"
            formatted += "------------------\n"

        return formatted

    async def _status_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'Operation failed')}"

        return output.get("output", "Operation completed successfully")

    async def _user_interaction_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'Failed to get user input')}"



        return ""

    async def _agent_message_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'Message delivery failed')}"


        return output.get("message", "")

    async def _conversation_end_formatter(self, output: Dict[str, Any]) -> str:
        return "Conversation has ended."
        
    async def _api_usage_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'API usage tracking failed')}"
            
        cost = output.get("cost", 0.0)
        return f"\n[API USAGE] Cost: ${cost:.6f}"
        
    async def _api_usage_summary_formatter(self, output: Dict[str, Any]) -> str:
        if not output.get("success", False):
            return f"Error: {output.get('error', 'API usage summary failed')}"
            
        total_cost = output.get("total_cost", 0.0)
        return f"\nTotal API Cost: ${total_cost:.6f}"

output_manager = OutputManager()
