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
        return iter((self.code, self.message or str(self.data)))
    
    @property
    def ok(self):
        return self.success

class Tool:
    def __init__(self, name: str, description: str, args: List[Argument], config: ToolConfig = None):
        self.name = name
        self.description = description
        self.args = args
        self.config = config or ToolConfig()

    def execute(self, **kwargs) -> ToolResult:
        try:
            args = self._validate_args(kwargs)
            result = self._run(args)
            if isinstance(result, tuple):
                # Assume tuple is (code, message)
                return ToolResult(success=(result[0] == ErrorCodes.SUCCESS), code=result[0], message=result[1])
            elif isinstance(result, ToolResult):
                return result
            else:
                return ToolResult(success=True, code=ErrorCodes.SUCCESS, data=result)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=str(e))

    def _validate_args(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        # Include all arguments, using the default value when not provided.
        return {arg.name: kwargs.get(arg.name, arg.default) for arg in self.args}

    def _run(self, args: Dict[str, Any]) -> Any:
        raise NotImplementedError
