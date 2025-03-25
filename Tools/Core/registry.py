import importlib
import inspect
import os
import pkgutil
from typing import Dict, List, Type, Optional
from pathlib import Path
from Tools.Core.tool import Tool

class ToolRegistry:
    """
    Tool discovery and registration system.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ToolRegistry, cls).__new__(cls)
            cls._instance._tools: Dict[str, Tool] = {}
            cls._instance._discovered = False
        return cls._instance
    
    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def get_all(self) -> Dict[str, Tool]:
        """Get all registered tools."""
        if not self._discovered:
            self.discover_tools()
        return self._tools
    
    def discover_tools(self) -> Dict[str, Tool]:
        """
        Discover all tool implementations in the Tools directory.
        """
        if self._discovered:
            return self._tools
            
        # Get the parent directory of Tools
        tools_dir = Path(__file__).parent.parent.parent
        
        # These are the directories to search for tools
        tool_dirs = [
            tools_dir / "File",
            tools_dir / "Special"
        ]
        
        for tool_dir in tool_dirs:
            if not tool_dir.exists() or not tool_dir.is_dir():
                continue
                
            package_name = ".".join(tool_dir.relative_to(tools_dir.parent).parts)
            
            for _, module_name, is_pkg in pkgutil.iter_modules([str(tool_dir)]):
                if module_name.startswith('__') or is_pkg:
                    continue
                    
                try:
                    module = importlib.import_module(f"{package_name}.{module_name}")
                    
                    # Find all Tool subclasses in the module
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, Tool) and 
                            obj != Tool and
                            not inspect.isabstract(obj)):
                            
                            # Create an instance and register it
                            try:
                                tool_instance = obj()
                                self.register(tool_instance)
                            except Exception as e:
                                print(f"Error instantiating tool {name}: {e}")
                                
                except ImportError as e:
                    print(f"Error importing module {module_name}: {e}")
        
        self._discovered = True
        return self._tools