from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type, Union
from pydantic import BaseModel, ValidationError, create_model

@dataclass
class ArgumentDefinition:
    """Describes an argument for a capability."""
    name: str
    type: str  # e.g., 'string', 'integer', 'boolean', 'float', 'filepath', 'object', 'array'
    required: bool = True
    description: str = ""
    default: Any = None
    # Optional: Add more validation constraints like enum, min/max, pattern

@dataclass
class CapabilityResult:
    """Standard result format from capability execution."""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None # Often used for error messages if success=False

class Capability(ABC):
    """Abstract Base Class for all MCP capabilities."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the capability."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the capability does."""
        pass

    @property
    @abstractmethod
    def arguments(self) -> List[ArgumentDefinition]:
        """List defining the arguments the capability accepts."""
        pass

    def get_argument_model(self) -> Type[BaseModel]:
        """Dynamically creates a Pydantic model for argument validation."""
        field_definitions = {}
        for arg in self.arguments:
            # Map simple types to Python types for Pydantic
            python_type: Type = str # Default to string
            if arg.type == 'integer':
                python_type = int
            elif arg.type == 'boolean':
                python_type = bool
            elif arg.type == 'float':
                python_type = float
            elif arg.type == 'object':
                python_type = Dict
            elif arg.type == 'array':
                python_type = List
            # Add more complex types (like 'filepath') or custom validators if needed

            if arg.required:
                field_definitions[arg.name] = (python_type, ...) # Ellipsis marks required fields
            else:
                field_definitions[arg.name] = (Optional[python_type], arg.default)

        # Create the model dynamically
        model_name = f"{self.name.capitalize()}Arguments"
        return create_model(model_name, **field_definitions) # type: ignore

    @abstractmethod
    def execute(self, args: BaseModel) -> CapabilityResult:
        pass
