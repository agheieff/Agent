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


            if "tool_name" not in result:
                result["tool_name"] = self.name


            if "success" not in result:
                result["success"] = True if "error" not in result or not result.get("error") else False
            if "output" not in result:
                result["output"] = ""
            if "error" not in result:
                result["error"] = ""
            if "exit_code" not in result:
                result["exit_code"] = 0 if result["success"] else 1


            if output_manager is not None:
                await output_manager.handle_tool_output(self.name, result)

            return result
        except Exception as e:
            logger.exception(f"Error executing tool {self.name}: {str(e)}")
            error_result = {
                "tool_name": self.name,
                "success": False,
                "output": "",
                "error": str(e),
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
