from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List

class ToolHandler(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

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
