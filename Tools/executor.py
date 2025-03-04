import importlib
import inspect
import logging
import sys
import os
from pathlib import Path
from typing import Dict, Any
import asyncio
import json

logger = logging.getLogger(__name__)

_TOOLS = {}
_INITIALIZED = False

def _init_tools():
    global _INITIALIZED
    if _INITIALIZED:
        return

    tools_dir = Path(__file__).parent
    root_dir = tools_dir.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    for directory in [d for d in tools_dir.iterdir() if d.is_dir() and not d.name.startswith('__')]:
        for py_file in directory.glob("**/*.py"):
            if py_file.name == "__init__.py":
                continue

            try:
                rel_path = py_file.relative_to(root_dir)
                module_path = '.'.join(rel_path.with_suffix('').parts)
                module = importlib.import_module(module_path)

                for name, obj in inspect.getmembers(module):
                    if inspect.isfunction(obj) and name.startswith('tool_'):
                        tool_name = name[5:]
                        _TOOLS[tool_name] = obj
                        logger.debug(f"Registered tool function: {tool_name}")

                    elif inspect.isclass(obj) and hasattr(obj, 'execute') and hasattr(obj, 'name'):
                        try:
                            instance = obj()
                            tool_name = getattr(instance, 'name', name.lower())
                            _TOOLS[tool_name] = instance.execute
                            logger.debug(f"Registered tool class: {tool_name}")
                        except Exception as e:
                            logger.warning(f"Failed to instantiate tool class {name}: {e}")

            except ImportError as e:
                logger.warning(f"Error importing module {module_path}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error registering tools from {py_file}: {e}")

    _INITIALIZED = True
    logger.info(f"Initialized {len(_TOOLS)} tools")

async def execute_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not _INITIALIZED:
        _init_tools()

    if tool_name not in _TOOLS:
        return {
            "output": "",
            "error": f"Unknown tool: {tool_name}",
            "success": False,
            "exit_code": 1
        }

    handler = _TOOLS[tool_name]
    logger.debug(f"Executing tool: {tool_name} with params: {params}")

    try:

        if hasattr(handler, '__self__') and hasattr(handler.__self__, 'run'):
            result = await handler.__self__.run(**params)
        elif inspect.iscoroutinefunction(handler):
            result = await handler(**params)
        else:

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: handler(**params))


        if isinstance(result, dict) and "success" in result:

            return {
                "output": result.get("output", ""),
                "error": result.get("error", ""),
                "success": result.get("success", True),
                "exit_code": result.get("exit_code", 0 if result.get("success", True) else 1),
                "tool_name": tool_name
            }
        elif isinstance(result, str):

            return {
                "output": result,
                "error": "",
                "success": True,
                "exit_code": 0,
                "tool_name": tool_name
            }
        elif isinstance(result, tuple):
            if len(result) == 2:
                output, success = result
                return {
                    "output": output,
                    "error": "" if success else "Tool execution failed",
                    "success": success,
                    "exit_code": 0 if success else 1,
                    "tool_name": tool_name
                }
            elif len(result) >= 3:
                output, error, exit_code = result[:3]
                return {
                    "output": output,
                    "error": error,
                    "success": exit_code == 0,
                    "exit_code": exit_code,
                    "tool_name": tool_name
                }
        else:

            return {
                "output": str(result),
                "error": "",
                "success": True,
                "exit_code": 0,
                "tool_name": tool_name
            }

    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {str(e)}", exc_info=True)
        return {
            "output": "",
            "error": str(e),
            "success": False,
            "exit_code": 1,
            "tool_name": tool_name
        }

def get_tool_metadata(tool_name: str) -> Dict[str, Any]:
    if not _INITIALIZED:
        _init_tools()

    if tool_name not in _TOOLS:
        return {
            "name": tool_name,
            "exists": False
        }

    handler = _TOOLS[tool_name]
    module = inspect.getmodule(handler)

    metadata = {
        "name": tool_name,
        "exists": True,
        "description": "",
        "usage": "",
        "examples": []
    }

    if module:

        for attr in ["TOOL_DESCRIPTION", "TOOL_HELP", "TOOL_EXAMPLES"]:
            if hasattr(module, attr):
                key = attr.lower()[5:]
                metadata[key] = getattr(module, attr)


    if handler.__doc__:
        metadata["docstring"] = handler.__doc__.strip()
        if not metadata["description"]:
            metadata["description"] = handler.__doc__.strip().split('\n')[0]

    return metadata

def list_available_tools() -> Dict[str, Dict[str, Any]]:
    if not _INITIALIZED:
        _init_tools()

    result = {}

    for tool_name in _TOOLS:
        result[tool_name] = get_tool_metadata(tool_name)

    return result

def get_tool_json_schema(tool_name: str) -> Dict[str, Any]:
\
\

    metadata = get_tool_metadata(tool_name)
    if not metadata["exists"]:
        return {"error": f"Tool {tool_name} not found"}

    schema = {
        "name": tool_name,
        "description": metadata.get("description", ""),
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "enum": [tool_name],
                "description": "Tool name"
            },
            "params": {
                "type": "object",
                "description": "Tool parameters",
                "properties": {}
            }
        }
    }


    usage = metadata.get("usage", "")
    if usage:

        param_pattern = r'(?:--|\[|\<)([\w_]+)(?:\>|\]|=)'
        params = re.findall(param_pattern, usage)
        for param in params:
            schema["properties"]["params"]["properties"][param] = {
                "type": "string",
                "description": f"Parameter: {param}"
            }

    return schema
