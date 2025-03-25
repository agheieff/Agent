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

class Tool:
    def __init__(self, name: str, description: str, args: List[Argument], config: ToolConfig = None):
        self.name = name
        self.description = description
        self.args = args
        self.config = config or ToolConfig()

    def execute(self, **kwargs):
        try:
            args = self._validate_args(kwargs)
            result = self._run(args)
            
            if isinstance(result, tuple):
                code, msg = result
                return ToolResult(code == ErrorCodes.SUCCESS, code, msg)
            return result if isinstance(result, ToolResult) else ToolResult(True, ErrorCodes.SUCCESS, data=result)
            
        except Exception as e:
            return ToolResult(False, ErrorCodes.UNKNOWN_ERROR, str(e))

    def _validate_args(self, kwargs):
        return {arg.name: kwargs.get(arg.name, arg.default) 
               for arg in self.args if not arg.optional or arg.name in kwargs}

    def _run(self, args):
        raise NotImplementedError
