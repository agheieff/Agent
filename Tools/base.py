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

    # --- Updated execute method ---
    def execute(self, **kwargs) -> ToolResult:
        """
        Validates arguments and runs the tool's main logic (_run).
        Catches general exceptions but specifically re-raises ConversationEnded.
        """
        validated_args_or_error = self._validate_args(kwargs)

        # 1. Check if validation failed and returned an error ToolResult
        if isinstance(validated_args_or_error, ToolResult) and not validated_args_or_error.ok:
            print(f"Tool {self.name}: Argument validation failed.")
            return validated_args_or_error # Return validation error directly

        # If validation passed, validated_args_or_error is the args dict
        args = validated_args_or_error

        try:
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
            # --- Catch all other exceptions from _run ---
            print(f"ERROR Tool Base Class ({self.name}): Caught exception during _run: {type(e).__name__} - {e}")
            traceback.print_exc() # Log the full traceback for debugging
            # Return a ToolResult indicating an unknown error
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=f"Tool execution error: {str(e)}")

    # --- Updated _validate_args ---
    def _validate_args(self, kwargs: Dict[str, Any]) -> Dict[str, Any] | ToolResult:
        """
        Validates received arguments against the tool's definition.

        Checks for missing required arguments. TODO: Add type checking.

        Returns:
            Dict[str, Any]: The validated arguments dictionary if successful.
            ToolResult: An error ToolResult if validation fails.
        """
        validated_args = {}
        missing_required = []
        received_keys = kwargs.keys()

        for arg_def in self.args:
            arg_name = arg_def.name
            if arg_name in received_keys:
                # Argument was provided
                validated_args[arg_name] = kwargs[arg_name]
                # TODO: Add type checking here based on arg_def.arg_type
            elif not arg_def.optional:
                # Required argument is missing
                missing_required.append(arg_name)
            else:
                # Optional argument missing, use default
                validated_args[arg_name] = arg_def.default

        if missing_required:
            # Return an error ToolResult immediately if required args are missing
            error_msg = f"Missing required arguments for tool '{self.name}': {', '.join(missing_required)}"
            print(f"Validation Error ({self.name}): {error_msg}")
            # Returning ToolResult here prevents _run being called with missing args
            return ToolResult(success=False, code=ErrorCodes.MISSING_REQUIRED_ARGUMENT, message=error_msg)

        # Placeholder for future type checking iteration
        # for name, value in validated_args.items():
        #     expected_type = ... get type from self.args ...
        #     if value is not None and not isinstance(value, expected_type):
        #          return ToolResult(..., code=ErrorCodes.INVALID_ARGUMENT_TYPE, ...)

        # Return the dictionary of arguments if all checks pass
        return validated_args


    def _run(self, args: Dict[str, Any]) -> Any:
        """Subclasses must implement this method."""
        raise NotImplementedError(f"Tool subclass '{self.__class__.__name__}' must implement the _run method.")
