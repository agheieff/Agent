from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Dict, Any, NamedTuple
import os

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
    default: Any = None

@dataclass 
class ToolConfig:
    allowed_in_test: bool = True
    requires_sudo: bool = False
    timeout: int = 30

class ErrorCode(IntEnum):
    SUCCESS = 0
    INVALID_INPUT = 1
    TOOL_FAILED = 2
    PERMISSION_DENIED = 3
    NOT_FOUND = 4
    
    @property
    def description(self):
        return {
            0: "Success",
            1: "Invalid input",
            2: "Tool execution failed",
            3: "Permission denied",
            4: "Resource not found"
        }.get(self.value, "Unknown error")

class ToolResult(NamedTuple):
    code: ErrorCode
    message: str = ""
    
    @property
    def ok(self):
        return self.code == ErrorCode.SUCCESS

class Tool:
    def __init__(self, name: str, description: str, args: List[Argument], config: ToolConfig = None):
        self.name = name
        self.description = description
        self.arguments = args
        self.config = config or ToolConfig()
        
    def execute(self, **kwargs) -> ToolResult:
        try:
            validated = self._validate_args(kwargs)
            return self._run(validated)
        except ValueError as e:
            return ToolResult(ErrorCode.INVALID_INPUT, str(e))
        except PermissionError:
            return ToolResult(ErrorCode.PERMISSION_DENIED, "Permission denied")
        except FileNotFoundError:
            return ToolResult(ErrorCode.NOT_FOUND, "File not found")
        except Exception as e:
            return ToolResult(ErrorCode.TOOL_FAILED, str(e))

    def _validate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        validated = {}
        for arg in self.arguments:
            if not arg.is_optional and arg.name not in args:
                raise ValueError(f"Missing required argument: {arg.name}")
            value = args.get(arg.name, arg.default)
            validated[arg.name] = self._validate_type(arg.name, value, arg.arg_type)
        return validated

    def _validate_type(self, name: str, value: Any, arg_type: ArgumentType) -> Any:
        if arg_type == ArgumentType.BOOLEAN:
            if isinstance(value, bool):
                return value
            if str(value).lower() in ('true', 'yes', '1'):
                return True
            if str(value).lower() in ('false', 'no', '0'):
                return False
            raise ValueError(f"Invalid boolean value for {name}")
        # Add other type validations...
        return value

    def _run(self, args: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError
