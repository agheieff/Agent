import inspect
import logging
import asyncio
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Assume _TOOLS is already populated externally.
_TOOLS: Dict[str, Any] = {}

async def execute_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    handler = _TOOLS.get(tool_name)
    if handler is None:
        return {
            "result": f"Unknown tool: {tool_name}",
            "exit_code": 1,
            "tool_name": tool_name
        }
    
    logger.debug(f"Executing tool: {tool_name} with params: {params}")
    try:
        if inspect.iscoroutinefunction(handler):
            result = await handler(**params)
        else:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: handler(**params))
        
        # Coerce non-dict results into a dictionary.
        if not isinstance(result, dict):
            result = {"exit_code": 0, "output": str(result)}
        
        exit_code = result.get("exit_code", 0)
        output = result.get("output", "")
        error = result.get("error", "")
        # Combine output and error: if exit_code is nonzero, return error.
        combined = output if exit_code == 0 else error
        
        return {
            "result": combined,
            "exit_code": exit_code,
            "tool_name": tool_name
        }
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
        return {
            "result": str(e),
            "exit_code": 1,
            "tool_name": tool_name
        }

async def execute_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = []
    for call in tool_calls:
        tool_name = call.get("name")
        params = call.get("params", {})
        result = await execute_tool(tool_name, params)
        results.append(result)
    return results
