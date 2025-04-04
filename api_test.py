#!/usr/bin/env python3
import os
import sys
import asyncio
import importlib
import inspect
from pathlib import Path
from typing import Dict, Any, Tuple, List

project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path: sys.path.insert(0, project_root)

from Clients.base import BaseClient, Message, ProviderConfig
import dotenv

dotenv.load_dotenv(Path(project_root) / '.env')

def get_providers() -> Dict[str, Tuple[Any, ProviderConfig]]:
    providers = {}
    api_dir = Path(project_root) / "Clients" / "API"
    for file_path in api_dir.glob("*.py"):
        if file_path.name.startswith("__"): continue
        name = file_path.stem
        module = importlib.import_module(f"Clients.API.{name}")
        cls, cfg = None, None
        for _, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient: cls = obj
            if isinstance(obj, ProviderConfig) and obj.name == name.lower(): cfg = obj
        if cls and cfg and os.getenv(cfg.api_key_env):
            providers[cfg.name] = (cls, cfg)
    return providers

async def main():
    print("Starting API Conversation Test")
    providers = get_providers()
    passed_count = 0
    tested_count = 0
    if not providers: print("WARN: No configured providers with API keys found."); return

    for name, (client_class, config) in providers.items():
        print(f"--- Provider: {name} ---")
        try: client = client_class(config=config)
        except TypeError: client = client_class()
        models = client.get_available_models()
        if not models: print(f"WARN:   No models found for {name}."); continue
        print(f"  Models: {', '.join(models)}")

        for model in models:
            tested_count += 1
            test_name = f"{name}/{model}"
            messages: List[Message] = []
            messages.append(Message("user", "Respond with ONLY the first letter of the alphabet in uppercase"))
            resp_a_raw = await client.chat_completion(messages=messages, model=model)
            resp_a = resp_a_raw.strip()
            if resp_a != "A":
                raise ValueError(f"FAIL: {test_name} - Step 1: Expected 'A', got '{resp_a}'")
            messages.append(Message("assistant", resp_a_raw))

            messages.append(Message("user", "Now respond with ONLY the next one"))
            resp_b_raw = await client.chat_completion(messages=messages, model=model)
            resp_b = resp_b_raw.strip()
            if resp_b != "B":
                raise ValueError(f"FAIL: {test_name} - Step 2: Expected 'B', got '{resp_b}'")

            print(f"  PASS: {test_name}")
            passed_count += 1

    print("\n" + "="*25 + " Summary " + "="*25)
    print(f"Total Models Tested Successfully: {tested_count}")
    print(f"All Passed: {passed_count}")
    print("="*59)

if __name__ == "__main__":
    asyncio.run(main())
