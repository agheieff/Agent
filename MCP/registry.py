import importlib
import inspect
import os
import pkgutil
import logging
from typing import Dict, Optional, Type
from pathlib import Path

from .capabilities.base import Capability

logger = logging.getLogger(__name__)

class CapabilityRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CapabilityRegistry, cls).__new__(cls)
            cls._instance._capabilities: Dict[str, Capability] = {}
            cls._instance._discovered = False
        return cls._instance

    def register(self, capability_instance: Capability) -> None:
        if capability_instance.name in self._capabilities:
            logger.warning(f"Overwriting capability registration for '{capability_instance.name}'")
        self._capabilities[capability_instance.name] = capability_instance
        logger.debug(f"Registered capability: {capability_instance.name}")

    def get(self, name: str) -> Optional[Capability]:
        if not self._discovered:
            self.discover_capabilities()
        return self._capabilities.get(name)

    def get_all(self) -> Dict[str, Capability]:
        if not self._discovered:
            self.discover_capabilities()
        return self._capabilities

    def discover_capabilities(self) -> None:
        if self._discovered:
            return

        logger.info("Discovering MCP capabilities...")
        capabilities_pkg_path = Path(__file__).parent / "capabilities"
        package_name = "MCP.capabilities" # The import path

        for _, module_name, is_pkg in pkgutil.iter_modules([str(capabilities_pkg_path)]):
            if is_pkg or module_name == "base": # Don't try to load packages or the base module itself
                continue

            try:
                module_import_path = f"{package_name}.{module_name}"
                module = importlib.import_module(module_import_path)

                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                            issubclass(obj, Capability) and
                            obj is not Capability and
                            not inspect.isabstract(obj)):
                        try:
                            instance = obj() # Instantiate the capability
                            self.register(instance)
                        except Exception as e:
                            logger.error(f"Failed to instantiate capability '{name}' from {module_import_path}: {e}", exc_info=True)

            except ImportError as e:
                logger.error(f"Failed to import capability module '{module_name}': {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error discovering capabilities in '{module_name}': {e}", exc_info=True)

        self._discovered = True
        logger.info(f"Capability discovery complete. Found: {list(self._capabilities.keys())}")

# Initialize registry singleton instance
capability_registry = CapabilityRegistry()
