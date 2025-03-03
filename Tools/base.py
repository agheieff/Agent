from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
import logging

# Import output manager - we use a try/except to handle circular imports
# or cases where OutputManager hasn't been initialized yet
try:
    from Output import output_manager
except (ImportError, ModuleNotFoundError):
    output_manager = None

logger = logging.getLogger(__name__)

class ToolHandler(ABC):
    name: str = ""
    description: str = ""

    # Optional formatter name for this tool's output
    formatter: str = "default"

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
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
        Run the tool and send its output to the output manager.

        This method wraps the execute method, adding output management.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            The result from execute()
        """
        try:
            # Execute the tool
            result = await self.execute(**kwargs)

            # Send result to output manager if available
            if output_manager is not None:
                await output_manager.handle_tool_output(self.name, result)

            return result
        except Exception as e:
            logger.exception(f"Error executing tool {self.name}: {str(e)}")
            error_result = {
                "success": False,
                "output": "",
                "error": str(e)
            }

            # Send error to output manager if available
            if output_manager is not None:
                await output_manager.handle_tool_output("error", error_result)

            return error_result

class FileTool(ToolHandler):
    async def validate_file_path(self, file_path: str) -> Tuple[bool, Optional[str]]:
        import os

        if not file_path:
            return False, "No file path provided"

        parent_dir = os.path.dirname(os.path.abspath(file_path))
        if not os.path.exists(parent_dir):
            return False, f"Directory does not exist: {parent_dir}"

        return True, None

class NetworkTool(ToolHandler):
    async def validate_url(self, url: str) -> Tuple[bool, Optional[str]]:
        import re

        if not url:
            return False, "No URL provided"

        url_pattern = re.compile(
            r'^(?:http|ftp)s?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            r'(?::\d+)?'
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        if not url_pattern.match(url):
            return False, f"Invalid URL format: {url}"

        return True, None

class SystemTool(ToolHandler):
    async def validate_command(self, command: str) -> Tuple[bool, Optional[str]]:
        if not command:
            return False, "No command provided"

        dangerous_patterns = [
            "rm -rf /", "mkfs", "> /dev/", "dd if=/dev/zero of=/dev/sda"
        ]

        for pattern in dangerous_patterns:
            if pattern in command:
                return False, f"Potentially dangerous command detected: {pattern}"

        return True, None
