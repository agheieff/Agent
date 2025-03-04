from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import logging
import inspect

try:
    from Output.output_manager import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolHandler(ABC):
    name: str = ""
    description: str = ""
    usage: str = ""
    examples: List[Tuple[str, str]] = []
    formatter: str = "default"

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        pass

    async def run(self, **kwargs) -> Dict[str, Any]:
        try:
            param_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
            logger.info(f"Executing tool {self.name} with parameters: {param_str}")
            result = await self.execute(**kwargs)
            result["tool_name"] = self.name
            exit_code = result.get("exit_code", 0)
            result["exit_code"] = exit_code
            combined = result.get("output", "") if exit_code == 0 else result.get("error", "")
            result["result"] = combined
            result.pop("success", None)
            if output_manager is not None:
                await output_manager.handle_tool_output(self.name, result)
            return result
        except Exception as e:
            logger.exception(f"Error executing tool {self.name}: {e}")
            error_result = {
                "tool_name": self.name,
                "result": str(e),
                "exit_code": 1
            }
            if output_manager is not None:
                await output_manager.handle_tool_output(self.name, error_result)
            return error_result

    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        return {
            "name": cls.name or cls.__name__.lower(),
            "description": cls.description,
            "usage": cls.usage,
            "examples": cls.examples,
            "formatter": cls.formatter,
            "docstring": cls.__doc__ or ""
        }

class FileTool(ToolHandler):
    pass

class NetworkTool(ToolHandler):
    pass

class SystemTool(ToolHandler):
    pass
