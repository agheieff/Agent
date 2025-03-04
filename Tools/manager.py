import logging
import asyncio
import json
from typing import List, Dict, Any, Tuple

from Tools.executor import execute_tool
from Core.composer import ToolResponseComposer

try:
    from Output.output_manager import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self.composer = ToolResponseComposer()
        self.agent_config: Dict[str, Any] = {}
        self.agent_llm = None
        self.agent_conversation_history: List[Dict[str, Any]] = []

    def set_agent_context(self, config: Dict[str, Any], llm, conversation_ref: List[Dict[str, Any]]):
        self.agent_config = config
        self.agent_llm = llm
        self.agent_conversation_history = conversation_ref

    async def process_message_from_calls(self, tool_calls: List[Dict[str, Any]]) -> str:
\
\
\
\

        if not tool_calls:
            return ""

        results = []
        for call in tool_calls:
            tool_name = call.get("name")
            params = call.get("params", {})

            logger.info(f"Executing tool: {tool_name} with params: {params}")


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


            if tool_name.lower() in ["telegram_send", "telegram_view"]:
                params["config"] = self.agent_config


            tool_result = await execute_tool(tool_name, params)
            results.append((tool_name, params, tool_result))


        summary = self.composer.compose_response(results)
        return summary
