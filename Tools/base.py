from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Any, Optional
from Tools.error_codes import ErrorCodes

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
    is_optional: bool = False
    default_value: Any = None

@dataclass
class ToolConfig:
    allowed_in_test_mode: bool = True
    requires_sudo: bool = False

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
    def __init__(self, name: str, description: str, help_text: str,
                 arguments: List[Argument], config: ToolConfig = None):
        self.name = name
        self.description = description
        self.help_text = help_text
        self.arguments = arguments
        self.config = config or ToolConfig()

    def execute(self, *args, **kwargs):
        try:
            # Convert positional args to keyword args based on argument names
            for i, arg in enumerate(args):
                if i < len(self.arguments):
                    kwargs[self.arguments[i].name] = arg
                    
            validated = self._validate_args(kwargs)
            result = self._execute(**validated)
            
            # Convert tuple (code, message) to ToolResult for test compatibility
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
            return ToolResult(ok=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _validate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        validated = {}
        for arg in self.arguments:
            if not arg.is_optional and arg.name not in args:
                raise ValueError(f"Missing required argument: {arg.name}")
            value = args.get(arg.name, arg.default_value)
            validated[arg.name] = value
        return validated

    def _execute(self, **kwargs):
        """
        Subclasses must override this method. Should return either:
          - (ErrorCodes.X, "Message") tuple
          - Or a ToolResult object
          - Or any other object indicating success
        """
        raise NotImplementedError
