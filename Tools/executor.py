import importlib
import inspect
import logging
import sys
import os
from pathlib import Path
from typing import Dict, Any
import asyncio

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

                    elif inspect.isclass(obj) and hasattr(obj, 'execute'):
                        try:
                            instance = obj()
                            tool_name = getattr(instance, 'name', name.lower())
                            _TOOLS[tool_name] = instance.execute
                        except:
                            pass

            except ImportError:
                pass

    _INITIALIZED = True

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

    try:
        # If handler is a method of a ToolHandler instance, use its run method
        if hasattr(handler, '__self__') and isinstance(handler.__self__, object) and hasattr(handler.__self__, 'run'):
            result = await handler.__self__.run(**params)
        # Otherwise, directly call the function
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
                "exit_code": result.get("exit_code", 0 if result.get("success", True) else 1)
            }
        elif isinstance(result, str):
            return {
                "output": result,
                "error": "",
                "success": True,
                "exit_code": 0
            }
        elif isinstance(result, tuple):
            if len(result) == 2:
                output, success = result
                return {
                    "output": output,
                    "error": "" if success else "Tool execution failed",
                    "success": success,
                    "exit_code": 0 if success else 1
                }
            elif len(result) >= 3:
                output, error, exit_code = result[:3]
                return {
                    "output": output,
                    "error": error,
                    "success": exit_code == 0,
                    "exit_code": exit_code
                }
        else:
            return {
                "output": str(result),
                "error": "",
                "success": True,
                "exit_code": 0
            }

    except Exception as e:
        return {
            "output": "",
            "error": str(e),
            "success": False,
            "exit_code": 1
        }
