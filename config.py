# ./config.py
"""
Central configuration file for the multi-agent system.
"""

import os
from pathlib import Path
from typing import Dict, Optional, List

# Try importing the dataclasses; handle potential ImportError if run standalone
try:
    from Clients.base import ProviderConfig, ModelConfig, PricingTier
except ImportError:
    # Define dummy classes if run standalone or imports fail initially
    print("Warning: Could not import dataclasses from Clients.base. Using dummy definitions.")
    from dataclasses import dataclass, field

    @dataclass
    class PricingTier:
        input: float = 0.0
        output: float = 0.0
        input_cache_miss: float = 0.0
        output_cache_miss: float = 0.0
        discount_hours: Optional[tuple] = None
        discount_rate: float = 0.0

    @dataclass
    class ModelConfig:
        name: str
        context_length: int
        pricing: PricingTier

    @dataclass
    class ProviderConfig:
        name: str
        api_base: str
        api_key_env: str
        models: Dict[str, ModelConfig]
        default_model: str
        requires_import: Optional[str] = None


# --- Agent Filesystem ---
PROJECT_ROOT = Path(__file__).parent.resolve()
_default_agent_fs_root = PROJECT_ROOT / "Agent_internal"
AGENT_FS_ROOT = Path(os.getenv("AGENT_FS_ROOT", str(_default_agent_fs_root))).resolve()
print(f"INFO: Using Agent Filesystem Root: {AGENT_FS_ROOT}")


AVAILABLE_PROVIDERS: Dict[str, ProviderConfig] = {

    "anthropic": ProviderConfig(
        name="anthropic",
        api_base="https://api.anthropic.com/v1", # Keep v1 for messages API
        api_key_env="ANTHROPIC_API_KEY",
        # Default model alias from the initial anthropic.py
        default_model="claude-3-7-sonnet",
        requires_import="anthropic",
        models={
            # Model alias -> ModelConfig
            "claude-3-7-sonnet": ModelConfig(
                # API Name from the initial anthropic.py
                # Note: Verify if "-latest" is a valid/current Anthropic API identifier
                name="claude-3-7-sonnet-latest",
                context_length=200000,
                pricing=PricingTier(input=3.00, output=15.00) # $/Million tokens
            ),
             "claude-3-5-sonnet": ModelConfig(
                # API Name from the initial anthropic.py
                # Note: Verify if "-latest" is a valid/current Anthropic API identifier
                name="claude-3-5-sonnet-latest",
                context_length=200000,
                pricing=PricingTier(input=3.00, output=15.00) # $/Million tokens
            ),
        }
    ),

    "deepseek": ProviderConfig(
        name="deepseek",
        api_base="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        requires_import="openai",
        models={
            # Model alias -> ModelConfig
            "deepseek-chat": ModelConfig(
                name="deepseek-chat",
                context_length=32768,
                pricing=PricingTier(
                    input=0.07, output=1.10, input_cache_miss=0.27,
                    discount_hours=(16.5, 0.5), discount_rate=0.50
                )
            ),
            "deepseek-reasoner": ModelConfig(
                name="deepseek-reasoner",
                context_length=32768,
                pricing=PricingTier(
                    input=0.14, output=2.19, input_cache_miss=0.55,
                    discount_hours=(16.5, 0.5), discount_rate=0.75
                )
            ),
        }
    ),
}

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "5"))

def get_provider_config(provider_name: str) -> Optional[ProviderConfig]:
    """Gets the configuration for a specific provider."""
    return AVAILABLE_PROVIDERS.get(provider_name.lower())

def get_model_config(provider_name: str, model_alias_or_name: str) -> Optional[ModelConfig]:
    """
    Gets the configuration for a specific model within a provider,
    checking both alias and actual model name.
    """
    provider_conf = get_provider_config(provider_name)
    if provider_conf:
        if model_alias_or_name in provider_conf.models:
            return provider_conf.models[model_alias_or_name]
        for alias, model_conf in provider_conf.models.items():
            if model_conf.name == model_alias_or_name:
                return model_conf
        if model_alias_or_name == provider_conf.default_model:
             return provider_conf.models.get(provider_conf.default_model)

    print(f"Warning: Model config not found for provider='{provider_name}', model='{model_alias_or_name}'")
    return None

def get_available_provider_names() -> List[str]:
    """Returns a list of configured provider names."""
    return list(AVAILABLE_PROVIDERS.keys())

def get_available_model_names(provider_name: str) -> List[str]:
    """Returns a list of model aliases for a given provider."""
    provider_conf = get_provider_config(provider_name)
    if provider_conf:
        return list(provider_conf.models.keys())
    return []

try:
    AGENT_FS_ROOT.mkdir(parents=True, exist_ok=True)
except OSError as e:
    print(f"Error: Could not create agent filesystem root at {AGENT_FS_ROOT}: {e}")
