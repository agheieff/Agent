from typing import Dict, List
from Clients.base import BaseClient, ProviderConfig, ModelConfig, Message

CONFIG = ProviderConfig(
    name="openai",
    api_base="https://api.openai.com/v1",
    api_key_env="OPENAI_API_KEY",
    default_model="gpt-4",
    models={
        "gpt-4": ModelConfig(
            name="gpt-4",
            context_length=8192,
            pricing={"input": 0.03, "output": 0.06}
        ),
        "gpt-3.5": ModelConfig(
            name="gpt-3.5-turbo",
            context_length=4096,
            pricing={"input": 0.0015, "output": 0.002}
        )
    }
)

class OpenAIClient(BaseClient):
    def __init__(self, config=CONFIG):
        super().__init__(config)

    def _initialize_client(self):
        from openai import OpenAI
        return OpenAI(api_key=self.api_key)

    def _call_api(self, **kwargs):
        return self.client.chat.completions.create(**kwargs)

    def _process_response(self, response):
        return response.choices[0].message.content
