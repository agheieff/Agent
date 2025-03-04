import logging
import asyncio
import json
import datetime
from typing import List, Dict, Any, Tuple, Optional

from Tools.executor import execute_tool, get_tool_metadata, list_available_tools
from Core.composer import ToolResponseComposer

try:
    from Output.output_manager import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolManager:
    """
    Manager for handling tool execution and response formatting.
    """

    def __init__(self):
        """Initialize the tool manager."""
        self.composer = ToolResponseComposer()
        self.agent_config: Dict[str, Any] = {}
        self.agent_llm = None
        self.agent_conversation_history: List[Dict[str, Any]] = []
        self.conversation_start_time = datetime.datetime.now()
        self.last_compact_time = self.conversation_start_time
        self.turn_counter = 0
        self.total_tokens_used = 0

    def set_agent_context(self, config: Dict[str, Any], llm, conversation_ref: List[Dict[str, Any]]):
        """Set the agent context for tool execution."""
        self.agent_config = config
        self.agent_llm = llm
        self.agent_conversation_history = conversation_ref

    def update_tokens_used(self, additional_tokens: int):
        """Update the token usage counter."""
        self.total_tokens_used += additional_tokens
        self.composer.update_token_count(additional_tokens)

    async def process_message_from_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        output_format: str = "text"
    ) -> str:
        """Process tool calls from a parsed message and return formatted results."""
        if not tool_calls:
            return ""

        self.turn_counter += 1
        results = []
        
        for call in tool_calls:
            if isinstance(call, dict) and "name" in call:
                tool_name = call.get("name")
                params = call.get("params", {})
            else:
                # Handle tuple format (legacy)
                tool_name, params, _unused = call

            logger.info(f"Executing tool: {tool_name} with params: {params}")

            # Check for internet access if disabled
            if not self.agent_config.get("agent", {}).get("allow_internet", True):
                netlike = {"curl", "web_client", "search_engine"}
                if tool_name in netlike or "url" in params:
                    results.append((tool_name, params, {
                        "success": False,
                        "error": "Internet access disabled",
                        "output": "",
                        "exit_code": 1
                    }))
                    continue

            # Check for compact tool to update last_compact_time
            if tool_name == "compact":
                self.last_compact_time = datetime.datetime.now()
            
            # Add configuration to certain tools
            if tool_name.lower() in ["telegram_send", "telegram_view"]:
                params["config"] = self.agent_config
                
            # Add agent context to certain tools
            if tool_name.lower() in ["compact", "archive"]:
                params["conversation_history"] = self.agent_conversation_history
                params["llm"] = self.agent_llm

            # Execute the tool
            start_time = datetime.datetime.now()
            tool_result = await execute_tool(tool_name, params)
            execution_time = (datetime.datetime.now() - start_time).total_seconds()
            
            # Add conversation tracking information
            tool_result["execution_time"] = f"{execution_time:.2f}s"
            tool_result["conversation_turn"] = self.turn_counter
            tool_result["tokens_used"] = self.total_tokens_used
            tool_result["elapsed_time"] = str(datetime.datetime.now() - self.conversation_start_time)
            tool_result["time_since_compact"] = str(datetime.datetime.now() - self.last_compact_time)
            
            results.append((tool_name, params, tool_result))

        # Create output in the appropriate format
        if output_format == "json":
            summary = self.composer.compose_response(results, format_name="json")
            
            # For JSON, parse and add additional metadata before re-serializing
            try:
                summary_dict = json.loads(summary)
                summary_dict["conversation_stats"] = {
                    "turn": self.turn_counter,
                    "tokens_used": self.total_tokens_used,
                    "elapsed_time": str(datetime.datetime.now() - self.conversation_start_time),
                    "time_since_compact": str(datetime.datetime.now() - self.last_compact_time),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                summary = json.dumps(summary_dict, indent=2)
            except json.JSONDecodeError:
                logger.warning("Failed to add metadata to JSON response")
        else:
            summary = self.composer.compose_response(results, format_name="text")
            
            # Add a timestamp and statistics footer to text output
            summary += f"\n--- Conversation Statistics ---\n"
            summary += f"Turn: {self.turn_counter}\n"
            summary += f"Tokens used: {self.total_tokens_used}\n"
            summary += f"Elapsed time: {datetime.datetime.now() - self.conversation_start_time}\n"
            summary += f"Time since last compact: {datetime.datetime.now() - self.last_compact_time}\n"
            summary += f"Timestamp: {datetime.datetime.now().isoformat()}\n"

        return summary
        
    async def get_tool_help(self, tool_name: str) -> Dict[str, Any]:
        """Get help information for a specific tool."""
        metadata = get_tool_metadata(tool_name)
        
        if not metadata["exists"]:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' not found",
                "output": "",
                "tool_name": tool_name
            }
            
        return {
            "success": True,
            "error": "",
            "output": f"Tool: {tool_name}\n\nDescription: {metadata.get('description', '')}\n\nUsage: {metadata.get('usage', '')}",
            "tool_name": tool_name,
            "metadata": metadata
        }
        
    async def list_tools(self) -> Dict[str, Any]:
        """List all available tools."""
        tools = list_available_tools()
        
        categories = {
            "file": [],
            "system": [],
            "network": [],
            "message": [],
            "utility": []
        }
        
        # Categorize tools
        for name, metadata in tools.items():
            if name.startswith(("read", "write", "edit", "replace")):
                categories["file"].append(name)
            elif name.startswith(("bash", "shell", "exec")):
                categories["system"].append(name)
            elif name.startswith(("curl", "http", "web")):
                categories["network"].append(name)
            elif name in ("message", "telegram_send", "telegram_view"):
                categories["message"].append(name)
            else:
                categories["utility"].append(name)
                
        return {
            "success": True,
            "error": "",
            "output": f"Available tools: {len(tools)}",
            "categories": categories,
            "tools": tools
        }
