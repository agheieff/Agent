import os
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from .error_codes import ErrorCodes
from .type_system import ArgumentType

# Re-export important types to simplify imports in tools
__all__ = [
    'Tool', 'Argument', 'ToolConfig', 'ErrorCodes', 'ArgumentType'
]

@dataclass
class Argument:
    name: str
    arg_type: ArgumentType = ArgumentType.STRING
    is_optional: bool = False
    description: Optional[str] = None
    default_value: Optional[Any] = None

@dataclass
class ToolConfig:
    allowed_in_test_mode: bool = False
    requires_sudo: bool = False
    requires_internet: bool = False
    examples: List[str] = field(default_factory=list)
    timeout: Optional[int] = None
    max_retries: int = 0
    id: Optional[str] = None
    output: Dict[str, bool] = field(default_factory=lambda: {
        'show_call': True,
        'show_exit_code': True,
        'show_output': False
    })

class Tool:
    def __init__(self,
                 name: Optional[str] = None,
                 description: Optional[str] = None,
                 help_text: Optional[str] = None,
                 arguments: Optional[List[Argument]] = None,
                 config: Optional[ToolConfig] = None):
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.help_text = help_text or self.description
        self.arguments = arguments or []
        self.config = config or ToolConfig()
        
    def execute(self, *args, **kwargs) -> tuple[int, Optional[str]]:
        """Execute the tool with the given arguments.
        
        Returns:
            tuple[int, Optional[str]]: A tuple containing (exit_code, error_message).
            If successful, error_message will be None.
        """
        try:
            # Process file path arguments if any exist
            for arg in self.arguments:
                if arg.arg_type == ArgumentType.FILEPATH and arg.name in kwargs:
                    kwargs[arg.name] = self._resolve_path(kwargs[arg.name])
                    
            return self._execute(*args, **kwargs)
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Error executing {self.name}: {str(e)}"
    
    def _resolve_path(self, path: str) -> str:
        """
        Resolve a file path to make it more intuitive for the agent.
        
        This method handles:
        1. Expanding ~ to the user's home directory
        2. Converting relative paths to absolute paths
        3. Normalizing paths to use consistent separators
        4. Making parent directory references (..) more understandable
        
        Args:
            path: The file path to resolve
            
        Returns:
            A resolved file path
        """
        # Expand user directory if path starts with ~
        if path.startswith('~'):
            path = os.path.expanduser(path)
        
        # If path is not absolute, make it relative to the current working directory
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        
        # Normalize path (resolve .. and . components and ensure consistent separators)
        path = os.path.normpath(path)
        
        return path
    
    def _execute(self, *args, **kwargs) -> tuple[int, Optional[str]]:
        """Execute the tool with the given arguments.
        
        This should be implemented by subclasses.
        
        Returns:
            tuple[int, Optional[str]]: A tuple containing (exit_code, error_message).
            If successful, error_message will be None.
        """
        raise NotImplementedError(f"Tool {self.name} does not implement _execute")
