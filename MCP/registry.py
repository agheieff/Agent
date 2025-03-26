import importlib
import inspect
import os
import pkgutil
import logging
from typing import Dict, Optional, Type
from pathlib import Path

# Ensure relative import works correctly
try:
    from .Operations.base import Operation
except ImportError:
    # Fallback for potential execution context issues (e.g., running tests directly)
    from Operations.base import Operation


logger = logging.getLogger(__name__)

class OperationRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OperationRegistry, cls).__new__(cls)
            cls._instance._operations: Dict[str, Operation] = {}
            cls._instance._discovered = False
        return cls._instance

    def register(self, operation_instance: Operation) -> None:
        if operation_instance.name in self._operations:
            logger.warning(f"Overwriting operation registration for '{operation_instance.name}'")
        self._operations[operation_instance.name] = operation_instance
        logger.debug(f"Registered operation: {operation_instance.name}")

    def get(self, name: str) -> Optional[Operation]:
        if not self._discovered:
            self.discover_operations()
        return self._operations.get(name)

    def get_all(self) -> Dict[str, Operation]:
        if not self._discovered:
            self.discover_operations()
        return self._operations.copy() # Return a copy

    def discover_operations(self) -> None:
        if self._discovered:
            return

        self._operations.clear() # Clear previous entries if re-discovering
        logger.info("Discovering MCP operations...")
        operations_pkg_path = Path(__file__).parent / "Operations" # Corrected directory name case
        package_name = "MCP.Operations" # Corrected import path case

        if not operations_pkg_path.is_dir():
             logger.warning(f"Operations directory not found at: {operations_pkg_path}")
             self._discovered = True
             return

        # Ensure the package itself is importable
        try:
             importlib.import_module(package_name)
        except ImportError as e:
             logger.error(f"Could not import base package '{package_name}': {e}", exc_info=True)
             # Decide if this is fatal or if we should continue
             # For now, let's assume it might be recoverable if submodules import differently
             # but log a clear error.

        for _, module_name, is_pkg in pkgutil.iter_modules([str(operations_pkg_path)]):
            # Skip __init__, base, and any sub-packages
            if module_name.startswith("_") or module_name == "base" or is_pkg:
                continue

            try:
                module_import_path = f"{package_name}.{module_name}"
                module = importlib.import_module(module_import_path)

                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                            issubclass(obj, Operation) and
                            obj is not Operation and
                            not inspect.isabstract(obj)):
                        try:
                            instance = obj() # Instantiate the operation
                            self.register(instance)
                        except TypeError as te: # Catch errors during instantiation (e.g., missing args in __init__)
                             logger.error(f"Failed to instantiate operation '{name}' from {module_import_path} - TypeError: {te}", exc_info=True)
                        except Exception as e:
                            logger.error(f"Failed to instantiate operation '{name}' from {module_import_path}: {e}", exc_info=True)

            except ImportError as e:
                logger.error(f"Failed to import operation module '{module_import_path}': {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error discovering operations in '{module_name}': {e}", exc_info=True)

        self._discovered = True
        logger.info(f"Operation discovery complete. Found: {list(self._operations.keys())}")

# Initialize registry singleton instance
operation_registry = OperationRegistry()
