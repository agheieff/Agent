from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import logging
import inspect

# Try to import output manager - we use a try/except to handle circular imports
try:
    from Output.output_manager import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolHandler(ABC):
    """
    Base class for tool handlers.
    
    All tools should either:
    1. Inherit from this class and implement the execute method, or
    2. Use the tool_* function pattern with appropriate metadata
    """
    name: str = ""  # Name of the tool
    description: str = ""  # Short description of the tool
    usage: str = ""  # Usage instructions
    examples: List[Tuple[str, str]] = []  # List of (example, description) tuples
    
    # Optional formatter name for this tool's output
    formatter: str = "default"

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool with the given parameters.

        This method should be implemented by subclasses.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            Dict with at least the following keys:
            - success: bool indicating if the tool execution was successful
            - output: str or object containing the tool output
            - error: str containing any error message (if success is False)
        """
        pass

    async def run(self, **kwargs) -> Dict[str, Any]:
        """
        Run the tool and handle its output.

        This method wraps the execute method, adding output management.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            The result from execute()
        """
        try:
            # Log the tool execution
            param_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
            logger.info(f"Executing tool {self.name} with parameters: {param_str}")
            
            # Execute the tool
            result = await self.execute(**kwargs)
            
            # Add tool name to result if not present
            if "tool_name" not in result:
                result["tool_name"] = self.name
                
            # Ensure required fields are present
            if "success" not in result:
                result["success"] = True if "error" not in result or not result.get("error") else False
            if "output" not in result:
                result["output"] = ""
            if "error" not in result:
                result["error"] = ""
            if "exit_code" not in result:
                result["exit_code"] = 0 if result["success"] else 1

            # Send result to output manager if available
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

            # Send error to output manager if available
            if output_manager is not None:
                await output_manager.handle_tool_output(self.name, error_result)

            return error_result
            
    @classmethod
    def get_metadata(cls) -> Dict[str, Any]:
        """
        Get metadata for this tool.
        
        Returns:
            Dictionary containing tool metadata
        """
        return {
            "name": cls.name or cls.__name__.lower(),
            "description": cls.description,
            "usage": cls.usage,
            "examples": cls.examples,
            "formatter": cls.formatter,
            "docstring": cls.__doc__ or ""
        }

# Simplified base class types without validators
class FileTool(ToolHandler):
    """Base class for tools that operate on files."""
    pass

class NetworkTool(ToolHandler):
    """Base class for tools that perform network operations."""
    pass

class SystemTool(ToolHandler):
    """Base class for tools that interact with the system."""
    pass
