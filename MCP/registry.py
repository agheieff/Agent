import importlib, inspect, os, pkgutil, logging
from typing import Dict, Optional, Type
from pathlib import Path
from .operations.base import Operation # UPDATED

logger = logging.getLogger(__name__)

class OperationRegistry: # RENAMED
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OperationRegistry, cls).__new__(cls)
            cls._instance._operations: Dict[str, Operation] = {} # RENAMED
            cls._instance._discovered = False
        return cls._instance

    def register(self, operation_instance: Operation) -> None: # RENAMED param
        if operation_instance.name in self._operations: # RENAMED var
            logger.warning(f"Overwriting operation registration for '{operation_instance.name}'")
        self._operations[operation_instance.name] = operation_instance # RENAMED var
        logger.debug(f"Registered operation: {operation_instance.name}")

    def get(self, name: str) -> Optional[Operation]:
        if not self._discovered:
            self.discover_operations() # RENAMED method call
        return self._operations.get(name) # RENAMED var

    def get_all(self) -> Dict[str, Operation]:
        if not self._discovered:
            self.discover_operations() # RENAMED method call
        return self._operations # RENAMED var

    def discover_operations(self) -> None: # RENAMED method
        if self._discovered:
            return

        logger.info("Discovering MCP operations...") # UPDATED log
        operations_pkg_path = Path(__file__).parent / "operations" # UPDATED path
        package_name = "MCP.operations" # UPDATED package name

        for _, module_name, is_pkg in pkgutil.iter_modules([str(operations_pkg_path)]):
            if is_pkg or module_name == "base":
                continue
            try:
                module_import_path = f"{package_name}.{module_name}"
                module = importlib.import_module(module_import_path)
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                            issubclass(obj, Operation) and # Check for Operation
                            obj is not Operation and
                            not inspect.isabstract(obj)):
                        try:
                            instance = obj()
                            self.register(instance) # Register the operation instance
                        except Exception as e:
                            logger.error(f"Failed to instantiate operation '{name}' from {module_import_path}: {e}", exc_info=True)
            # ... (rest of error handling) ...

        self._discovered = True
        logger.info(f"Operation discovery complete. Found: {list(self._operations.keys())}") # UPDATED log

# Initialize registry singleton instance
operation_registry = OperationRegistry() # RENAMED variable
