import importlib
import inspect
import pkgutil
import logging
from typing import Dict, Optional, Type
from pathlib import Path

# Use relative import assuming registry.py is inside MCP package
from .Operations.base import Operation

logger = logging.getLogger(__name__)

class OperationRegistry:
    """Singleton registry for discovering and accessing MCP Operations."""
    _instance = None
    _operations: Dict[str, Operation]
    _discovered: bool

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OperationRegistry, cls).__new__(cls)
            cls._instance._operations = {}
            cls._instance._discovered = False
            logger.debug("OperationRegistry singleton created.")
        return cls._instance

    def register(self, operation_instance: Operation) -> None:
        """Registers a single operation instance."""
        op_name = operation_instance.name
        if op_name in self._operations:
            # Allows re-registration, potentially useful for hot-reloading in dev
            logger.warning(f"Overwriting existing operation registration for '{op_name}'")
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
        return self._operations.copy() # Return a copy to prevent external modification

    def discover_operations(self, force_rediscover: bool = False) -> None:
        """
        Automatically discovers and registers Operation classes from modules
        within the 'MCP.Operations' directory (excluding 'base' and '__init__').
        """
        if self._discovered and not force_rediscover:
            return

        if force_rediscover:
             logger.info("Forcing re-discovery of MCP operations...")
             self._operations.clear()
        else:
             logger.info("Discovering MCP operations...")

        # Determine the path to the Operations package relative to this file
        try:
            # Assumes registry.py is in MCP/
            operations_pkg_path_obj = Path(__file__).parent / "Operations"
            package_name = "MCP.Operations" # The import path
            # Dynamically import the base package to ensure it's loaded
            operations_pkg = importlib.import_module(package_name)
            operations_pkg_path = operations_pkg_path_obj.resolve() # Get absolute path for iter_modules
        except (ImportError, FileNotFoundError) as e:
             logger.error(f"Could not find or import the '{package_name}' package: {e}", exc_info=True)
             self._discovered = True # Mark as discovered to avoid retrying constantly
             return

        if not operations_pkg_path.is_dir():
            logger.error(f"Operations directory not found at resolved path: {operations_pkg_path}")
            self._discovered = True
            return

        discovered_count = 0
        # Iterate over modules in the Operations directory
        for module_info in pkgutil.iter_modules([str(operations_pkg_path)]):
            module_name = module_info.name
            # Skip base class, private modules, and __init__
            if module_name == "base" or module_name.startswith("_") or module_name == "__init__":
                continue

            try:
                module_import_path = f"{package_name}.{module_name}"
                module = importlib.import_module(module_import_path)

                # Inspect the module for classes inheriting from Operation
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                            issubclass(obj, Operation) and
                            obj is not Operation and # Exclude the base class itself
                            not inspect.isabstract(obj)): # Exclude abstract classes
                        try:
                            instance = obj() # Instantiate the operation
                            self.register(instance)
                            discovered_count += 1
                        except Exception as e:
                             logger.error(f"Failed to instantiate operation '{name}' from {module_import_path}: {e}", exc_info=True)

            except ImportError as e:
                logger.error(f"Failed to import operation module '{module_import_path}': {e}", exc_info=True)
            except Exception as e:
                 logger.error(f"Unexpected error processing module '{module_name}': {e}", exc_info=True)

        self._discovered = True
        logger.info(f"Operation discovery complete. Found {discovered_count} operations: {list(self._operations.keys())}")


# Initialize the singleton instance upon module load
operation_registry = OperationRegistry()
