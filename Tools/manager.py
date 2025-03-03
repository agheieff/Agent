import logging
import asyncio
from typing import List, Dict, Any, Tuple, Optional

from Tools.parser import ToolParser
from Tools.executor import execute_tool
from Tools.composer import ToolResponseComposer

try:
    from Output.output_manager import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self.parser = ToolParser()
        self.composer = ToolResponseComposer()

    async def process_message(self, message: str) -> str:
        tool_calls = self.parser.extract_tool_calls(message)

        if not tool_calls:
            return ""

        results = []

        for tool_name, params, is_help in tool_calls:
            logger.info(f"Executing tool: {tool_name} with params: {params}, help={is_help}")

            if is_help:
                result = await execute_tool(tool_name, {"help": True})
            else:
                result = await execute_tool(tool_name, params)

            if output_manager:
                await output_manager.handle_tool_output(tool_name, result)
            
            results.append((tool_name, params, result))

        if results:
            return self.composer.compose_response(results)
        return ""

    async def execute_single_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        result = await execute_tool(tool_name, params)
        
        if output_manager:
            await output_manager.handle_tool_output(tool_name, result)
            
        return result

    async def execute_tools_concurrently(self, tool_requests: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
        async def _execute_tool(tool_name, params):
            result = await execute_tool(tool_name, params)
            
            if output_manager:
                await output_manager.handle_tool_output(tool_name, result)
                
            return tool_name, params, result

        tasks = [_execute_tool(name, params) for name, params in tool_requests]
        results = await asyncio.gather(*tasks)

        return results
