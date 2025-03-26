from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type, Union
from pydantic import BaseModel, ValidationError, create_model

@dataclass
class ArgumentDefinition:
    """Describes an argument for an operation."""
    name: str
    type: str  # e.g., 'string', 'integer', 'boolean', 'float', 'filepath', 'object', 'array'
    required: bool = True
    description: str = ""
    default: Any = None
    # Optional: Add more validation constraints like enum, min/max, pattern

@dataclass
class OperationResult:
    """Standard result format from operation execution."""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None # Often used for error messages if success=False

class Operation(ABC):
    """Abstract Base Class for all MCP operations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the operation."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the operation does."""
        pass

    @property
    @abstractmethod
    def arguments(self) -> List[ArgumentDefinition]:
        """List defining the arguments the operation accepts."""
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
        try:
            # Ensure Pydantic v2 compatibility if needed by checking BaseModel.__version__
            # For now, assume this works for the installed version.
            return create_model(model_name, **field_definitions) # type: ignore
        except Exception as e:
            # Handle potential errors during model creation, e.g., name conflicts
            # This is less likely with unique operation names but good practice
            raise RuntimeError(f"Failed to create argument model for {self.name}: {e}") from e


    @abstractmethod
    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        """
        Executes the operation's logic.

        Args:
            args: A Pydantic model instance containing validated arguments.
            agent_permissions: Dictionary containing relevant permissions for the agent
                               (e.g., {'file': [{'path_prefix': '/tmp/', 'permissions': ['read']}]}).

        Returns:
            An OperationResult object.

        Raises:
            MCPError: For expected, controlled errors during execution.
            Exception: For unexpected errors.
        """
        pass
