import importlib
import inspect
import pkgutil
import logging
from typing import Dict, Optional
from pathlib import Path

from .Operations.base import Operation

logger = logging.getLogger(__name__)

class OperationRegistry:
    """Registry for discovering and accessing MCP Operations."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OperationRegistry, cls).__new__(cls)
            cls._instance._operations = {}
            cls._instance._discovered = False
        return cls._instance

    def register(self, operation_instance: Operation) -> None:
        """Registers a single operation instance."""
        op_name = operation_instance.name
        self._operations[op_name] = operation_instance
        logger.debug(f"Registered operation: {op_name}")

    def get(self, name: str) -> Optional[Operation]:
        """Gets a registered operation instance by name."""
        if not self._discovered:
            self.discover_operations()
        return self._operations.get(name)

    def get_all(self) -> Dict[str, Operation]:
        """Gets a dictionary of all registered operation instances."""
        if not self._discovered:
            self.discover_operations()
        return self._operations.copy()

    def discover_operations(self) -> None:
        """Automatically discovers and registers Operation classes."""
        if self._discovered:
            return

        logger.info("Discovering MCP operations...")
        operations_pkg_path = Path(__file__).parent / "Operations"
        
        if not operations_pkg_path.is_dir():
            logger.error(f"Operations directory not found at: {operations_pkg_path}")
            self._discovered = True
            return

        for module_info in pkgutil.iter_modules([str(operations_pkg_path)]):
            module_name = module_info.name
            if module_name == "base" or module_name.startswith("_"):
                continue

            try:
                module = importlib.import_module(f"MCP.Operations.{module_name}")
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, Operation) and 
                        obj is not Operation and 
                        not inspect.isabstract(obj)):
                        
                        try:
                            instance = obj()
                            self.register(instance)
                        except Exception as e:
                            logger.error(f"Failed to instantiate operation '{name}': {e}")
            except Exception as e:
                logger.error(f"Error importing module '{module_name}': {e}")

        self._discovered = True
        logger.info(f"Operation discovery complete. Found {len(self._operations)} operations")

# Initialize the singleton instance
operation_registry = OperationRegistry()