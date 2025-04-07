from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Any, Optional
# Import ConversationEnded and ErrorCodes
from Tools.error_codes import ErrorCodes, ConversationEnded
import traceback # For debugging unexpected errors

class ArgumentType(Enum):
    STRING = auto()
    BOOLEAN = auto()
    INT = auto()
    FLOAT = auto()
    FILEPATH = auto()

@dataclass
class Argument:
    name: str
    arg_type: ArgumentType
    description: str = ""
    optional: bool = False
    default: Any = None

@dataclass
class ToolConfig:
    test_mode: bool = True
    needs_sudo: bool = False

@dataclass
class ToolResult:
    success: bool
    code: int
    message: str = ""
    data: Any = None

    def __iter__(self):
        # Allows unpacking like: code, msg = tool_result
        return iter((self.code, self.message or str(self.data)))

    @property
    def ok(self):
        # Convenience property
        return self.success

class Tool:
    def __init__(self, name: str, description: str, args: List[Argument], config: ToolConfig = None):
        self.name = name
        self.description = description
        self.args = args
        self.config = config or ToolConfig()

    def execute(self, **kwargs) -> ToolResult:
        """
        Validates arguments and runs the tool's main logic (_run).
        Catches general exceptions but specifically re-raises ConversationEnded.
        """
        try:
            # 1. Validate args (basic implementation - TODO: improve this)
            args = self._validate_args(kwargs)
            # If validation returned an error ToolResult, return it directly
            if isinstance(args, ToolResult) and not args.success:
                 return args

            # 2. Call the specific tool's implementation (_run)
            # This is where _run (like in End tool) might raise ConversationEnded or other exceptions
            result = self._run(args)

            # 3. Process the return value if _run completes normally
            if isinstance(result, tuple):
                # Assume tuple is (code, message) - potentially legacy? Prefer ToolResult.
                return ToolResult(success=(result[0] == ErrorCodes.SUCCESS), code=result[0], message=str(result[1]))
            elif isinstance(result, ToolResult):
                # Tool explicitly returned a ToolResult object (preferred)
                return result
            else:
                # Tool returned something else (or None), assume success
                return ToolResult(success=True, code=ErrorCodes.SUCCESS, data=result)

        except ConversationEnded as ce:
            # --- Specifically catch and re-raise ConversationEnded ---
            # Let it propagate up to Executor and Orchestrator
            raise ce
        except Exception as e:
            # --- Catch all other exceptions from _validate_args or _run ---
            print(f"ERROR Tool Base Class ({self.name}): Caught exception in execute: {type(e).__name__} - {e}")
            traceback.print_exc() # Log the full traceback for debugging
            # Return a ToolResult indicating an unknown error
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=f"Tool execution error: {str(e)}")

    def _validate_args(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Basic argument validation. Returns validated args dict or ToolResult on error.
        Currently only maps passed args to expected args with defaults.
        TODO: Add required argument checks and type validation.
        """
        validated_args = {}
        missing_required = []
        for arg in self.args:
            value = kwargs.get(arg.name, arg.default)
            if not arg.optional and value is None:
                # Check if it was explicitly passed as None vs just missing
                if arg.name not in kwargs:
                     missing_required.append(arg.name)
            validated_args[arg.name] = value

        if missing_required:
             # Return an error ToolResult immediately if required args are missing
             # NOTE: This check was missing before, potentially causing None errors in _run
             error_msg = f"Missing required arguments: {', '.join(missing_required)}"
             print(f"Validation Error ({self.name}): {error_msg}")
             # Returning ToolResult here prevents _run being called with missing args
             # We need to decide if execute should return this or raise Exception
             # Returning ToolResult seems cleaner for now.
             return ToolResult(success=False, code=ErrorCodes.MISSING_REQUIRED_ARGUMENT, message=error_msg)


        # Placeholder for future type checking based on arg.arg_type
        # for name, value in validated_args.items():
        #    ... type check logic ...

        return validated_args


    def _run(self, args: Dict[str, Any]) -> Any:
        """Subclasses must implement this method."""
        raise NotImplementedError(f"Tool subclass '{self.__class__.__name__}' must implement the _run method.")
