import os
import logging
from typing import Dict, List, Optional, Any
from Clients.base import BaseClient, ProviderConfig, ModelConfig, PricingTier, Message

GEMINI_CONFIG = ProviderConfig(
    name="gemini",
    api_base="https://generativelanguage.googleapis.com/v1",
    api_key_env="GOOGLE_API_KEY",
    default_model="gemini-pro",
    requires_import="google.generativeai",
    models={
        "gemini-pro": ModelConfig(
            name="gemini-pro",
            context_length=32768,
            pricing=PricingTier(input=0.00025, output=0.0005)
        ),
        "gemini-1.5-pro": ModelConfig(
            name="gemini-1.5-pro",
            context_length=1000000,
            pricing=PricingTier(input=0.00035, output=0.00105))
    }
)

class GeminiClient(BaseClient):
    def __init__(self, config=GEMINI_CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        import google.generativeai as genai
        genai.configure(api_key=self.api_key)
        return genai

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, str]]:
        return [{"role": msg.role, "parts": [msg.content]} 
                for msg in messages if msg.role != "system"]

    def _call_api(self, messages, model, **kwargs):
        model_obj = self.client.GenerativeModel(model_name=model)
        chat = model_obj.start_chat(history=self._format_messages(messages))
        return chat.send_message("", generation_config=kwargs)

    def _process_response(self, response):
        return response.text
