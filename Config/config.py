import os
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List

logger = logging.getLogger(__name__)

class Config:

    def __init__(self, config_path: Optional[Path] = None):
        self._config: Dict[str, Any] = {}
        self._config_path = config_path or self._find_config_file()
        self._load_config()

    def _find_config_file(self) -> Path:

        if os.environ.get("ARCADIA_CONFIG_PATH"):
            env_path = Path(os.environ.get("ARCADIA_CONFIG_PATH"))
            if env_path.exists():
                return env_path


        search_paths = [
            Path.cwd() / "Config" / "config.yaml",
            Path.cwd() / "config.yaml", 
            Path.home() / ".arcadia" / "config.yaml",
            Path(__file__).parent / "config.yaml"
        ]

        for path in search_paths:
            if path.exists():
                return path


        return Path(__file__).parent / "config.yaml"

    def _load_config(self):

        self._config = self._load_default_config()


        if self._config_path.exists():
            try:
                with open(self._config_path, 'r') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self._update_dict_recursive(self._config, file_config)
            except Exception as e:
                logger.error(f"Error loading config from {self._config_path}: {e}")


        self._apply_environment_variables()

    def _load_default_config(self) -> Dict[str, Any]:
        default_config_path = Path(__file__).parent / "defaults.yaml"

        if default_config_path.exists():
            try:
                with open(default_config_path, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Error loading default config: {e}")


        return {"agent": {"test_mode": False}}

    def _update_dict_recursive(self, target: Dict, source: Dict):
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._update_dict_recursive(target[key], value)
            else:
                target[key] = value

    def _apply_environment_variables(self):
        env_prefix = "ARCADIA_"

        for env_var, value in os.environ.items():
            if env_var.startswith(env_prefix):

                config_path = env_var[len(env_prefix):].lower().replace("_", ".")
                self.set(config_path, value)

    def get(self, path: str, default: Any = None) -> Any:
        parts = path.split('.')
        current = self._config

        try:
            for part in parts:
                current = current[part]
            return current
        except (KeyError, TypeError):
            return default

    def set(self, path: str, value: Any):
        parts = path.split('.')
        current = self._config


        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]


        if isinstance(value, str):
            if value.lower() in ('true', 'yes', 'y', '1'):
                value = True
            elif value.lower() in ('false', 'no', 'n', '0'):
                value = False
            elif value.isdigit():
                value = int(value)


        current[parts[-1]] = value

    def save(self, path: Optional[Path] = None):
        save_path = path or self._config_path

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w') as f:
                yaml.dump(self._config, f, default_flow_style=False)
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")

    def is_test_mode(self) -> bool:
        return self.get("agent.test_mode", False)

    def to_dict(self) -> Dict[str, Any]:
        return self._config.copy()



config = Config()

def get_test_mode() -> bool:
    return config.is_test_mode()
