import os
import re
import importlib.util
import inspect
from typing import Dict, List, Optional, Any, Tuple

def generate_command_execution_guide(p:str="openai")->str:
    """
    Generate a command execution guide specific to the provider.
    
    Args:
        p: Provider name (e.g., "openai", "anthropic", "deepseek")
        
    Returns:
        A string containing the command execution guide
    """
    p=p.lower()
    if p=="anthropic":
        return"""
Tool Execution Format:
tool_use:{
"name":"tool_name","input":{"param1":"value1"}}
"""
    elif p=="deepseek":
        return"""
Tool Execution Format:
{
"thinking":"hidden reasoning","reasoning":"explanation","action":"tool_name","action_input":{"param":"value"},"response":"text"
}
"""
    return"""
Tool Execution Format:
{
"thinking":"hidden reasoning","analysis":"explanation","tool_calls":[{"name":"tool_name","params":{"param":"value"}}],"answer":"text"
}
"""

def generate_agent_role_explanation()->str:
    """Generate the agent role explanation section of the system prompt."""
    return"""
# Agent Role
You are an autonomous agent with access to a variety of tools to help you accomplish tasks.
You should understand the user's requests and use the appropriate tools to respond effectively.
If you need to execute a command or perform an action, use the available tools rather than just explaining what you would do.
"""

def generate_file_path_guide()->str:
    """Generate guidance for working with file paths."""
    return"""
# Working with File Paths
When using tools that require file paths, follow these guidelines:

1. **Relative Paths**: 
   - Paths without a leading slash (e.g., `file.txt`, `docs/report.md`) are relative to the current working directory
   - You can use `./` prefix to explicitly indicate the current directory (e.g., `./file.txt`)
   - Use `../` to refer to the parent directory (e.g., `../file.txt`)

2. **Absolute Paths**:
   - Paths starting with a slash (e.g., `/home/user/file.txt`) refer to the exact location on the filesystem
   - You can use `~` to refer to the user's home directory (e.g., `~/Documents/file.txt`)

3. **Path Normalization**:
   - Paths are automatically normalized to use the correct separators for the operating system
   - Redundant separators and `.` references are resolved automatically

4. **Directory Actions**:
   - Use `ls` tool to list directory contents before performing file operations
   - When creating new files, ensure the parent directory exists first
"""

def generate_conversation_tracking()->str:
    """Generate the conversation tracking section of the system prompt."""
    return"""
# Conversation Flow
- Analyze user requests carefully to understand what tools are needed
- Use tools by following the Tool Execution Format specified above
- When a task is complete, summarize what you've done and ask if the user needs anything else
- If you can't accomplish something with the available tools, explain why and suggest alternatives
- Use @tool end when the conversation is complete and no further assistance is needed
"""

def get_tools_info() -> str:
    """
    Extract information about available tools in the Tools/ directory.
    
    Returns:
        A formatted string with the directory structure and tool descriptions.
    """
    result = []
    
    # Header for the tools section
    result.append("# Available Tools\n")
    result.append("Tools are functions you can use by writing `@tool <toolname>`. ")
    result.append("For example, to read a file, you can use `@tool read_file filename=\"path/to/file\"`.\n")
    
    # Get all tools and their descriptions
    tools_info = _scan_tools_directory("Tools")
    
    if not tools_info:
        result.append("No tools found in the Tools/ directory.")
        return "\n".join(result)
    
    # Format the tools directory structure
    result.append("## Tools Directory Structure\n")
    for dir_path, tools in sorted(tools_info.items()):
        # Skip empty directories or directories with no tools
        if not tools:
            continue
        
        result.append(f"### {dir_path}")
        for tool_name, tool_info in sorted(tools.items()):
            result.append(f"- `{tool_name}` ({tool_info['file']}): {tool_info['description']}")
        result.append("")  # Add blank line
    
    # Format tool details
    result.append("## Tool Descriptions\n")
    all_tools = []
    for dir_path, tools in tools_info.items():
        for tool_name, tool_info in tools.items():
            all_tools.append((tool_name, dir_path, tool_info))
    
    # Sort by tool name
    all_tools.sort(key=lambda x: x[0])
    
    for tool_name, dir_path, tool_info in all_tools:
        result.append(f"### @tool {tool_name}")
        result.append(f"**Directory**: {dir_path}")
        result.append(f"**File**: {tool_info['file']}")
        result.append(f"**Description**: {tool_info['description']}")
        
        # Add help text if available
        if 'help_text' in tool_info and tool_info['help_text']:
            result.append(f"**Help**: {tool_info['help_text']}")
        
        # Add arguments if available
        if 'arguments' in tool_info and tool_info['arguments']:
            result.append("\n**Arguments**:")
            for arg in tool_info['arguments']:
                optional_str = " (optional)" if arg.get('optional', False) else ""
                
                default_value = arg.get('default', None)
                if default_value is not None:
                    if default_value.strip() in ["None", "''", '""']:
                        default_str = ""
                    else:
                        default_str = f", default: {default_value}"
                else:
                    default_str = ""
                
                description = arg.get('description', 'No description')
                result.append(f"- `{arg['name']}`{optional_str}{default_str}: {description}")
        
        result.append("")  # Add blank line
    
    return "\n".join(result)

def _scan_tools_directory(base_dir: str) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Scan the Tools directory for tool modules and extract information about them.
    
    Args:
        base_dir: The base directory to start scanning from
        
    Returns:
        A dictionary mapping directory paths to tools information
    """
    result = {}
    base_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), base_dir)
    
    if not os.path.isdir(base_path):
        return result
    
    # Recursively scan directories
    for root, dirs, files in os.walk(base_path):
        # Skip __pycache__ directories
        if "__pycache__" in root:
            continue
        
        # Get relative path from the base_dir
        rel_path = os.path.relpath(root, os.path.dirname(base_path))
        if rel_path == ".":
            rel_path = base_dir
        
        # Dict to store tools in this directory
        tools_in_dir = {}
        
        # Process Python files
        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                file_path = os.path.join(root, file)
                module_name = file[:-3]  # Remove .py extension
                
                # Extract tools from the module
                tools = _extract_tools_from_module(file_path, rel_path, module_name)
                tools_in_dir.update(tools)
        
        # Add to result if there are tools in this directory
        if tools_in_dir:
            result[rel_path] = tools_in_dir
    
    return result

def _extract_tools_from_module(file_path: str, dir_path: str, module_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Extract tool classes from a module.
    
    Args:
        file_path: Path to the module file
        dir_path: Relative path to the directory containing the module
        module_name: Name of the module
        
    Returns:
        A dictionary mapping tool names to tool information
    """
    result = {}
    
    try:
        # Import the module dynamically
        spec = importlib.util.spec_from_file_location(f"{dir_path}.{module_name}", file_path)
        if spec is None or spec.loader is None:
            return result
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Look for Tool classes
        for name, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and hasattr(obj, "name") and hasattr(obj, "description"):
                try:
                    # Create an instance to get the tool info
                    instance = obj()
                    
                    # Basic tool info
                    tool_info = {
                        "file": os.path.basename(file_path),
                        "description": instance.description,
                    }
                    
                    # Add help text if available
                    if hasattr(instance, "help_text"):
                        tool_info["help_text"] = instance.help_text
                    
                    # Add arguments if available
                    if hasattr(instance, "arguments"):
                        args_info = []
                        for arg in instance.arguments:
                            arg_info = {
                                "name": arg.name,
                                "description": arg.description,
                                "optional": arg.is_optional,
                            }
                            
                            # Add default value if available
                            if hasattr(arg, "default_value") and arg.default_value is not None:
                                if isinstance(arg.default_value, str):
                                    arg_info["default"] = f'"{arg.default_value}"'
                                else:
                                    arg_info["default"] = str(arg.default_value)
                            
                            args_info.append(arg_info)
                        
                        tool_info["arguments"] = args_info
                    
                    # Add to result
                    result[instance.name] = tool_info
                except Exception as e:
                    # Skip tools that can't be instantiated
                    pass
    
    except Exception as e:
        # Skip modules that can't be imported
        pass
    
    return result

def generate_system_prompt(provider:str="openai", config_path=None, summary_path=None) -> str:
    """
    Generate a complete system prompt for the agent.
    
    Args:
        provider: The model provider (e.g., "openai", "anthropic", "deepseek")
        config_path: Optional path to a configuration file
        summary_path: Optional path to a summary file
        
    Returns:
        A formatted string containing the full system prompt
    """
    parts = []
    
    # Add command execution guide specific to the provider
    parts.append(generate_command_execution_guide(provider))
    
    # Add agent role explanation
    parts.append(generate_agent_role_explanation())
    
    # Add file path guidance
    parts.append(generate_file_path_guide())
    
    # Add conversation tracking guidance
    parts.append(generate_conversation_tracking())
    
    # Add tools information
    parts.append(get_tools_info())
    
    # Combine all parts with line breaks
    return "\n\n".join(parts)
