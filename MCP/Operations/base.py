from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type, Union
from pydantic import BaseModel, ValidationError, create_model

@dataclass
class ArgumentDefinition:
    """Describes an argument for an operation."""
    name: str
    type: str
    required: bool = True
    description: str = ""
    default: Any = None

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
            python_type: Type = str
            if arg.type == 'integer': python_type = int
            elif arg.type == 'boolean': python_type = bool
            elif arg.type == 'float': python_type = float
            elif arg.type == 'object': python_type = Dict
            elif arg.type == 'array': python_type = List

            if arg.required:
                field_definitions[arg.name] = (python_type, ...)
            else:
                field_definitions[arg.name] = (Optional[python_type], arg.default)

        model_name = f"{self.name.capitalize()}Arguments"
        # Ensure model names are unique if needed, though dynamic creation usually handles this.
        # Add try-except block if there's potential for name collision errors.
        return create_model(model_name, **field_definitions) # type: ignore

    @abstractmethod
    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        """
        Executes the operation's logic.

        Args:
            args: A Pydantic model instance containing validated arguments.
            agent_permissions: Dictionary containing relevant permissions for the agent.

        Returns:
            An OperationResult object.

        Raises:
            MCPError: For expected, controlled errors during execution.
            Exception: For unexpected errors.
        """
        pass
