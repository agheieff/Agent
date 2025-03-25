from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Any

class ArgumentType(Enum):
    STRING = auto()
    BOOLEAN = auto()
    INT = auto()
    FLOAT = auto()
    FILEPATH = auto()

@dataclass 
class Argument:
    name: str
    type: ArgumentType
    description: str = ""
    optional: bool = False
    default: Any = None

class Tool:
    def __init__(self, name: str, description: str, args: List[Argument]):
        self.name = name
        self.description = description 
        self.args = args

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            validated = self._validate_args(kwargs)
            return {"success": True, "result": self._run(validated)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _validate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            arg.name: args.get(arg.name, arg.default)
            for arg in self.args 
            if not arg.optional or arg.name in args
        }

    def _run(self, args: Dict[str, Any]):
        raise NotImplementedError
