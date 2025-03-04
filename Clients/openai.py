from openai import OpenAI
import logging
from typing import Dict, Optional
from .base import BaseLLMClient, ModelInfo

logger = logging.getLogger(__name__)

class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key: str):
        super().__init__(api_key)

    def _initialize_client(self, api_key: str) -> None:
        try:
            self.client = OpenAI(api_key=api_key)
            logger.info("OpenAI client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing OpenAI client: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to initialize OpenAI client: {str(e)}")

    def _register_models(self) -> None:

        self.models["gpt-4.5-preview"] = ModelInfo(
            name="GPT-4.5 Preview",
            api_name="gpt-4.5-preview",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=75.0,
            output_price=150.0,
            input_cache_read_price=37.5,
            input_cache_write_price=75.0
        )

        self.models["gpt-4o"] = ModelInfo(
            name="GPT-4o",
            api_name="gpt-4o",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=2.5,
            output_price=10.0,
            input_cache_read_price=1.25,
            input_cache_write_price=2.5
        )

        self.models["o1"] = ModelInfo(
            name="o1",
            api_name="o1",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=15.0,
            output_price=60.0,
            input_cache_read_price=7.5,
            input_cache_write_price=15.0
        )

        self.models["o3-mini"] = ModelInfo(
            name="o3-mini",
            api_name="o3-mini",
            supports_reasoning=True,
            prefers_separate_system_prompt=True,
            context_window=128000,
            input_price=1.1,
            output_price=4.4,
            input_cache_read_price=0.55,
            input_cache_write_price=1.1
        )

        self.default_model = "o1"
