from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Type, Union
from pydantic import BaseModel, create_model, Field

# Type alias for common types
ArgType = Union[str, int, bool, float, Dict[str, Any], List[Any]]

@dataclass
class ArgumentDefinition:
    """Describes an argument for an MCP operation."""
    name: str
    type: str  # 'string', 'integer', 'boolean', 'float', 'object', 'array', 'filepath'
    required: bool = True
    description: str = ""
    default: Any = None

@dataclass
class OperationResult:
    """Standard result format from operation execution."""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None

    @classmethod
    def success_result(cls, data: Any = None, message: Optional[str] = None) -> 'OperationResult':
        """Convenience method to create a successful result."""
        return cls(success=True, data=data, message=message)
    
    @classmethod
    def error_result(cls, message: str, data: Any = None) -> 'OperationResult':
        """Convenience method to create an error result."""
        return cls(success=False, data=data, message=message)

class Operation(ABC):
    """Base Class for all MCP operations."""
    name: str = NotImplemented
    description: str = NotImplemented
    arguments: List[ArgumentDefinition] = NotImplemented
    
    def __init__(self):
        self._argument_model = None
    
    def get_argument_model(self) -> Type[BaseModel]:
        """Creates a Pydantic model for argument validation."""
        if self._argument_model is not None:
            return self._argument_model
            
        # Map argument types to Python types
        type_mapping = {
            'string': str, 'integer': int, 'boolean': bool, 
            'float': float, 'object': Dict[str, Any], 
            'array': List[Any], 'filepath': str
        }
        
        # Build field definitions for the Pydantic model
        field_definitions = {}
        for arg in self.arguments:
            python_type = type_mapping.get(arg.type, str)
            
            if arg.required:
                field_definitions[arg.name] = (python_type, ...)
            else:
                field_definitions[arg.name] = (Optional[python_type], Field(default=arg.default))
        
        # Create and cache the model
        model_name = f"{self.name.title().replace('_', '')}Args"
        self._argument_model = create_model(model_name, **field_definitions)
        return self._argument_model
    
    @abstractmethod
    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        """Execute the operation with validated arguments."""
        pass