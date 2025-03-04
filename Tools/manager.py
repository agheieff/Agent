import logging
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from Core.parser import ToolParser
from Tools.executor import execute_tool
from Core.composer import ToolResponseComposer

try:
    from Output.output_manager import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self.parser = ToolParser()
        self.composer = ToolResponseComposer()

        self.agent_config = None
        self.agent_llm = None
        self.agent_conversation_history = None

    def set_agent_context(self, config: Dict[str, Any], llm, conversation_ref: List[Dict]):
        self.agent_config = config
        self.agent_llm = llm
        self.agent_conversation_history = conversation_ref

    async def process_message(self, message: str) -> str:
        tool_calls = self.parser.extract_tool_calls(message)
        if not tool_calls:
            return ""

        results = []

        for tool_name, params, is_help in tool_calls:
            logger.info(f"Executing tool: {tool_name} with params: {params}, help={is_help}")


            if self.agent_config:
                allow_inet = self.agent_config.get("agent", {}).get("allow_internet", True)
                if not allow_inet:
                    net_tools = {"curl", "search_engine", "internet_tool", "web_client"}
                    if tool_name.lower() in net_tools or "url" in params or "internet" in tool_name.lower():
                        logger.warning("Internet access is disabled; blocking this tool call.")
                        result = {
                            "output": "",
                            "error": "Internet access is disabled in config. This tool call is blocked.",
                            "success": False,
                            "exit_code": 1
                        }
                        results.append((tool_name, params, result))
                        continue


            if tool_name.lower() == "compact":
                params["conversation_history"] = self.agent_conversation_history
                params["llm"] = self.agent_llm


            if tool_name.lower() in ["telegram_send", "telegram_view"]:
                params["config"] = self.agent_config


            tool_result = await execute_tool(tool_name, params)


            if self.agent_llm and hasattr(self.agent_llm, "total_tokens"):
                used_tokens = self.agent_llm.total_tokens
                max_tokens = getattr(self.agent_llm, "max_model_tokens", 128000)
                percent = (used_tokens / max_tokens) * 100.0
                usage_str = f"[Status: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Used {used_tokens}/{max_tokens} ({percent:.2f}%)]"
                if tool_result.get("output"):
                    tool_result["output"] += f"\n\n{usage_str}"
                else:
                    tool_result["output"] = usage_str

            if output_manager:
                await output_manager.handle_tool_output(tool_name, tool_result)

            results.append((tool_name, params, tool_result))

        if results:
            return self.composer.compose_response(results)
        return ""

    async def execute_single_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        result = await execute_tool(tool_name, params)

        if self.agent_llm and hasattr(self.agent_llm, "total_tokens"):
            used_tokens = self.agent_llm.total_tokens
            max_tokens = getattr(self.agent_llm, "max_model_tokens", 128000)
            percent = (used_tokens / max_tokens) * 100.0
            stamp = f"[Status: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Used {used_tokens}/{max_tokens} ({percent:.2f}%)]"
            if result.get("output"):
                result["output"] += f"\n\n{stamp}"
            else:
                result["output"] = stamp

        if output_manager:
            await output_manager.handle_tool_output(tool_name, result)

        return result

    async def execute_tools_concurrently(self, tool_requests: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
        async def _execute_tool(tn, pm):
            return await self.execute_single_tool(tn, pm)

        tasks = [_execute_tool(name, params) for name, params in tool_requests]
        results_raw = await asyncio.gather(*tasks)

        results = []
        for (tool_name, params), tool_result in zip(tool_requests, results_raw):
            results.append((tool_name, params, tool_result))

        return results
