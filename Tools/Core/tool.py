from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Type
from inspect import signature, Parameter
from enum import Enum

from Tools.error_codes import ErrorCodes

@dataclass
class ToolResult:
    ok: bool
    code: int
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    
    def __iter__(self):
        # Allow unpacking like a tuple (code, message)
        return iter((self.code, self.message))

class Tool:
    """Base class for all tools."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self._registry = None
    
    def execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with the given arguments.
        This performs argument validation before calling the _execute method.
        """
        try:
            # Validate arguments here if needed
            result = self._execute(**kwargs)
            
            # Handle different return types
            if isinstance(result, tuple) and len(result) == 2:
                code, message = result
                ok = (code == ErrorCodes.SUCCESS)
                return ToolResult(ok=ok, code=code, message=message)
            elif isinstance(result, ToolResult):
                return result
            else:
                # If it's not a 2-tuple or ToolResult, treat as success with data
                return ToolResult(ok=True, code=ErrorCodes.SUCCESS, data=result)
                
        except Exception as e:
            return ToolResult(
                ok=False,
                code=ErrorCodes.UNKNOWN_ERROR,
                message=f"Tool execution failed: {str(e)}"
            )
    
    def _execute(self, **kwargs):
        """
        Subclasses must override this method.
        Should return either:
          - (ErrorCodes.X, "Message") tuple
          - Or a ToolResult object
          - Or any other object indicating success
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement _execute")
    
    def get_parameters(self) -> List[Dict[str, Any]]:
        """Get parameter definitions for this tool."""
        params = []
        sig = signature(self._execute)
        
        for name, param in sig.parameters.items():
            if name == 'self':
                continue
                
            has_default = param.default is not Parameter.empty
            params.append({
                'name': name,
                'required': not has_default,
                'default': None if not has_default else param.default,
                'description': getattr(param, 'description', f"Parameter: {name}")
            })
            
        return params