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

@dataclass
class Tool:
    name: str
    description: str
    args: List[Argument]

    def execute(self, **kwargs) -> Dict[str, Any]:
        try:
            validated = self._validate_args(kwargs)
            return {"success": True, "result": self._run(validated)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _validate_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        validated = {}
        for arg in self.args:
            if not arg.optional and arg.name not in args:
                raise ValueError(f"Missing required argument: {arg.name}")
            validated[arg.name] = args.get(arg.name, arg.default)
        return validated

    def _run(self, args: Dict[str, Any]):
        raise NotImplementedError
