from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel, create_model, Field

@dataclass
class ArgumentDefinition:
    """Describes an argument for an MCP operation."""
    name: str
    type: str  # 'string', 'integer', 'boolean', 'float', 'object', 'array'
    required: bool = True
    description: str = ""
    default: Any = None

@dataclass
class OperationResult:
    """Standard result format from operation execution."""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None

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
            
        type_mapping = {
            'string': str, 'integer': int, 'boolean': bool, 
            'float': float, 'object': Dict[str, Any], 
            'array': List[Any], 'filepath': str
        }
        
        field_definitions = {}
        for arg in self.arguments:
            python_type = type_mapping.get(arg.type, str)
            
            if arg.required:
                field_definitions[arg.name] = (python_type, ...)
            else:
                field_definitions[arg.name] = (Optional[python_type], Field(default=arg.default))
        
        model_name = f"{self.name.title().replace('_', '')}Args"
        self._argument_model = create_model(model_name, **field_definitions)
        return self._argument_model
    
    @abstractmethod
    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        """Execute the operation with validated arguments."""
        pass