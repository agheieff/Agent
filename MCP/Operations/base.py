from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type, Union
from pydantic import BaseModel, ValidationError, create_model, Field

@dataclass
class ArgumentDefinition:
    """Describes an argument for an MCP operation."""
    name: str
    type: str  # e.g., 'string', 'integer', 'boolean', 'float', 'filepath', 'object', 'array'
    required: bool = True
    description: str = ""
    default: Any = None
    # Example: constraints: Optional[Dict[str, Any]] = None # {'enum': ['a', 'b'], 'min': 0}

@dataclass
class OperationResult:
    """Standard result format from operation execution."""
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None # Often used for error messages if success=False

class Operation(ABC):
    """Abstract Base Class for all MCP operations."""

    # Using class attributes for metadata, enforced by abstract properties
    name: str = NotImplemented
    description: str = NotImplemented
    arguments: List[ArgumentDefinition] = NotImplemented

    def __init__(self):
        # Basic validation on instantiation
        if self.name is NotImplemented or not self.name:
            raise NotImplementedError(f"Operation subclass {self.__class__.__name__} must define a 'name'.")
        if self.description is NotImplemented:
             raise NotImplementedError(f"Operation subclass {self.__class__.__name__} must define a 'description'.")
        if self.arguments is NotImplemented:
             raise NotImplementedError(f"Operation subclass {self.__class__.__name__} must define 'arguments'.")

        # Cache the generated model type
        self._argument_model: Optional[Type[BaseModel]] = None

    def get_argument_model(self) -> Type[BaseModel]:
        """
        Dynamically creates and caches a Pydantic model for argument validation
        based on the operation's 'arguments' definition.
        """
        if self._argument_model is not None:
            return self._argument_model

        field_definitions = {}
        type_mapping = {
            'string': str,
            'integer': int,
            'boolean': bool,
            'float': float,
            'object': Dict[str, Any],
            'array': List[Any],
            'filepath': str, # Can add custom validation later if needed
        }

        for arg in self.arguments:
            python_type = type_mapping.get(arg.type)
            if python_type is None:
                 raise TypeError(f"Unsupported argument type '{arg.type}' defined for '{arg.name}' in operation '{self.name}'.")

            if arg.required:
                # Create a required field (no default value provided to create_model)
                 field_definitions[arg.name] = (python_type, ...)
            else:
                # Create an optional field with a default value
                # Pydantic needs 'Optional[type]' for optional fields unless default is None
                field_definitions[arg.name] = (Optional[python_type], Field(default=arg.default))


        # Create the Pydantic model dynamically
        model_name = f"{self.name.replace('_', ' ').title().replace(' ', '')}Arguments"
        try:
            self._argument_model = create_model(model_name, **field_definitions) # type: ignore
            return self._argument_model
        except Exception as e:
            # Handle potential errors during model creation (e.g., invalid defaults)
            raise RuntimeError(f"Failed to create Pydantic argument model for '{self.name}': {e}") from e


    @abstractmethod
    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        """
        Executes the core logic of the operation.

        Args:
            args: A Pydantic model instance containing validated arguments.
            agent_permissions: Dictionary containing permissions context for the agent
                               (e.g., {'file_permissions': [...]}).

        Returns:
            An OperationResult object.

        Raises:
            MCPError: For expected, controlled errors during execution (e.g., permission denied, file not found).
            Exception: For unexpected internal errors. The server should catch these.
        """
        pass
