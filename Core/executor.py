import os
import importlib.util
import re
from typing import Tuple, Any, Dict, List, Optional
from Tools.base import Tool, Argument, ErrorCodes
from Tools.type_system import ArgumentType, validate_and_convert

class Executor:
    def __init__(self, tools_dir="Tools"):
        self.tools_dir = tools_dir
        
    def _parse_tool_call(self, call_text: str) -> Tuple[str, Dict[str, str]]:
        # Updated pattern to handle empty args and spaces better
        pattern = r'@tool\s+(\w+)(?:\s+)?(.*?)@end'
        match = re.search(pattern, call_text, re.DOTALL)
        if not match:
            raise ValueError("Invalid tool call format")
            
        tool_name = match.group(1).strip()
        args_text = match.group(2).strip()
        
        args = {}
        if args_text:
            for line in args_text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if ':' not in line:
                    raise ValueError(f"Invalid argument format: {line}")
                key, value = line.split(':', 1)
                args[key.strip()] = value.strip()
            
        return tool_name, args
    
    def _import_tool(self, tool_name: str) -> Any:
        for root, dirs, files in os.walk(self.tools_dir):
            for file in files:
                if file.endswith('.py') and file != '__init__.py':
                    module_path = os.path.join(root, file)
                    spec = importlib.util.spec_from_file_location(
                        f"tool_{tool_name}", module_path
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Look for a class that matches the tool name
                        for item_name in dir(module):
                            item = getattr(module, item_name)
                            if (hasattr(item, '__init__') and 
                                hasattr(item, 'execute') and
                                getattr(item(), 'name', '').lower() == tool_name.lower()):
                                return item
                                
        raise ImportError(f"Could not find tool: {tool_name}")
    
    def _validate_and_convert_args(self, tool_instance: Any, string_args: Dict[str, str]) -> Dict[str, Any]:
        """
        Validate and convert string arguments based on the tool's argument definitions.
        """
        arg_defs: List[Argument] = tool_instance.arguments
        processed_args = {}
        
        # Create a map of argument names to their definitions
        arg_map = {arg.name: arg for arg in arg_defs}
        
        # Check for missing required arguments
        for arg_def in arg_defs:
            if not arg_def.is_optional and arg_def.name not in string_args:
                if arg_def.default_value is not None:
                    processed_args[arg_def.name] = arg_def.default_value
                else:
                    raise ValueError(f"Missing required argument: {arg_def.name}")
        
        # Process and validate provided arguments
        for arg_name, arg_value in string_args.items():
            # Check if this is a defined argument
            if arg_name not in arg_map:
                raise ValueError(f"Unknown argument: {arg_name}")
            
            arg_def = arg_map[arg_name]
            
            # Convert and validate the argument based on its type
            try:
                processed_args[arg_name] = validate_and_convert(arg_value, arg_def.arg_type)
            except ValueError as e:
                raise ValueError(f"Invalid value for {arg_name}: {str(e)}")
                
        return processed_args
    
    def execute(self, call_text: str) -> Tuple[int, str]:
        try:
            # Parse the call
            tool_name, string_args = self._parse_tool_call(call_text)
            
            # Import the tool
            tool_class = self._import_tool(tool_name)
            
            # Create instance
            tool_instance = tool_class()
            
            # Validate and convert arguments
            processed_args = self._validate_and_convert_args(tool_instance, string_args)
            
            # Execute the tool with processed arguments
            return tool_instance.execute(**processed_args)
            
        except ValueError as e:
            return -1, f"Invalid tool call: {str(e)}"
        except ImportError as e:
            return -1, str(e)
        except Exception as e:
            return -1, f"Error executing tool: {str(e)}" 