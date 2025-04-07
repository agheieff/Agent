import asyncio
import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import traceback

from Clients.base import BaseClient, ProviderConfig
from Core.agent_config import AgentConfiguration
from Core.agent_instance import AgentInstance
from Core.executor import Executor
from Tools.error_codes import ConversationEnded, ErrorCodes
from Prompts.main import build_system_prompt, discover_tools, Tool
from Core.utils import get_multiline_input

def load_agent_configurations(config_dir: str = "./AgentConfigs") -> List[AgentConfiguration]:
    print(f"Loading agent configurations from: {config_dir}")
    configs = []
    config_path = Path(config_dir)
    if not config_path.is_dir():
        print(f"Warning: Configuration directory '{config_dir}' not found.")
        return []
    default_config_data = {}
    default_file = config_path / "default_agent.yaml"
    if default_file.exists():
        try:
            with open(default_file, 'r') as f:
                default_config_data = yaml.safe_load(f) or {}
            print(f"  Loaded defaults from {default_file.name}")
        except Exception as e:
            print(f"Warning: Failed to load default config '{default_file.name}': {e}")
    for file_path in config_path.glob("*.yaml"):
        if file_path.name == "default_agent.yaml":
            continue
        try:
            with open(file_path, 'r') as f:
                agent_data = yaml.safe_load(f)
                if not agent_data or not isinstance(agent_data, dict):
                     print(f"Warning: Skipping invalid or empty YAML file: {file_path.name}")
                     continue
                final_data = default_config_data.copy()
                final_data.update(agent_data)
                if 'agent_id' not in final_data:
                     final_data['agent_id'] = file_path.stem
                     print(f"Warning: 'agent_id' not found in {file_path.name}, using filename '{final_data['agent_id']}'.")
                if 'role' not in final_data:
                     final_data['role'] = final_data['agent_id']
                final_data.setdefault('model_provider', 'deepseek')
                final_data.setdefault('model_name', 'deepseek-chat')
                final_data.setdefault('system_prompt', f"You are an AI assistant with the role: {final_data['role']}.")
                final_data.setdefault('allowed_tools', [])
                config = AgentConfiguration(
                    agent_id=final_data['agent_id'],
                    role=final_data['role'],
                    model_provider=final_data['model_provider'],
                    model_name=final_data['model_name'],
                    system_prompt=final_data['system_prompt'],
                    allowed_tools=final_data['allowed_tools'],
                )
                configs.append(config)
                print(f"  Loaded config for agent: {config.agent_id} (Provider: {config.model_provider}, Model: {config.model_name})")
        except Exception as e:
            print(f"Error loading or parsing config file {file_path.name}: {e}")
            traceback.print_exc()
    if not configs:
         raise ValueError("Failed to load any valid agent configurations.")
    return configs


class Orchestrator:
    def __init__(self, config_list: List[AgentConfiguration]):
        self.agents: Dict[str, AgentInstance] = {}
        self.clients: Dict[str, BaseClient] = {}
        self.executor = Executor()
        self.all_discovered_tools: Dict[str, Tool] = {}
        print("Initializing Orchestrator...")
        self.all_discovered_tools = discover_tools()
        print(f"Orchestrator discovered tools: {list(self.all_discovered_tools.keys())}")
        self._initialize_clients(config_list)
        self._create_agents(config_list)

    def _initialize_clients(self, config_list: List[AgentConfiguration]):
        print("Initializing LLM clients...")
        providers_needed = {cfg.model_provider for cfg in config_list}
        for provider_name in providers_needed:
            if provider_name not in self.clients:
                try:
                    api_dir = Path(__file__).parent.parent / "Clients" / "API"
                    module = importlib.import_module(f"Clients.API.{provider_name}")
                    client_class, provider_config = None, None
                    config_name_const = f"{provider_name.upper()}_CONFIG"
                    for name, obj in inspect.getmembers(module):
                        if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient and name.lower() == f"{provider_name}client": client_class = obj
                        if isinstance(obj, ProviderConfig) and name == config_name_const: provider_config = obj
                    if not client_class: raise ValueError(f"Client class not found for {provider_name}")
                    if not provider_config: raise ValueError(f"ProviderConfig const not found for {provider_name}")
                    api_key = os.getenv(provider_config.api_key_env)
                    if not api_key: print(f"Warning: API key {provider_config.api_key_env} not found.")
                    sig = inspect.signature(client_class.__init__)
                    if 'config' in sig.parameters: client_instance = client_class(config=provider_config)
                    else: client_instance = client_class()
                    self.clients[provider_name] = client_instance
                    print(f"  Initialized client for: {provider_name}")
                except Exception as e: print(f"Error initializing client for {provider_name}: {e}")

    def _create_agents(self, config_list: List[AgentConfiguration]):
        print("Creating agent instances...")
        for config in config_list:
            if config.agent_id in self.agents:
                print(f"Warning: Duplicate agent_id '{config.agent_id}'. Skipping.")
                continue
            client = self.clients.get(config.model_provider)
            if not client:
                print(f"Warning: Client for provider '{config.model_provider}' not initialized. Cannot create agent '{config.agent_id}'.")
                continue
            try:
                agent_instance = AgentInstance(config, client, self.executor, self.all_discovered_tools)
                self.agents[config.agent_id] = agent_instance
            except Exception as e:
                print(f"Unexpected error creating agent '{config.agent_id}': {e}")
                traceback.print_exc()

    async def run_main_loop(self, initial_prompt: str, target_agent_id: str = "ceo", max_turns: int = 10):
        print(f"\n--- Starting Main Loop (Target: {target_agent_id}, Max Turns: {max_turns}) ---")
        agent = self.agents.get(target_agent_id)
        if not agent:
            print(f"Error: Target agent '{target_agent_id}' not found.")
            return

        agent.add_message('user', initial_prompt)
        print(f"\nUser (to {target_agent_id}): {initial_prompt}")

        turn_count = 0
        try:
            while turn_count < max_turns:
                print(f"\n--- Turn {turn_count + 1}/{max_turns} ({target_agent_id}) ---")

                if agent.messages and agent.messages[-1].role == 'assistant':
                    agent.add_message('user', "Proceed.")

                result = await agent.execute_turn()
                turn_count += 1

                print(f"DEBUG Orchestrator: Checking pause flag for agent '{agent.config.agent_id}'. Flag is: {agent.pause_requested_by_tool}") # DEBUG
                if agent.pause_requested_by_tool:
                    print(f"DEBUG Orchestrator: Pause flag is True. Entering pause handling.") # DEBUG
                    agent.pause_requested_by_tool = False # Reset flag

                    pause_message = "Agent paused. Please provide input or press Enter to continue."
                    if agent.messages and agent.messages[-1].role == 'assistant' and agent.messages[-1].content.startswith("@result pause"):
                         try:
                             lines = agent.messages[-1].content.split('\n')
                             for line in lines:
                                 if line.startswith("output: "):
                                      pause_message = line.split("output: ", 1)[1].strip()
                                      break
                         except Exception as parse_err:
                              print(f"Warning: Error parsing pause message from result: {parse_err}")

                    print("\n-----------------------------------------------------")
                    print(f"[Orchestrator] {pause_message}")
                    print("-----------------------------------------------------")
                    user_input = get_multiline_input("> ")

                    if user_input is None:
                        print("\nExiting loop due to user input (EOF).")
                        break
                    elif user_input.strip():
                        print(f"User (to {target_agent_id}): {user_input}")
                        agent.add_message('user', user_input)
                    else:
                        print("[Empty input received. Resuming autonomous run...]")

                    print(f"DEBUG Orchestrator: Continuing loop after pause handling.") # DEBUG
                    continue

                if isinstance(result, str) and result.startswith("[ERROR:"):
                    print(f"\n[Orchestrator] Agent '{target_agent_id}' reported error. Stopping loop.")
                    break

                if result == "" and agent.messages and not agent.messages[-1].content.startswith("@result"):
                     print(f"\n[Orchestrator] Agent '{target_agent_id}' produced no text output. Stopping loop.")
                     break

                if turn_count >= max_turns:
                    print(f"\n[Orchestrator] Reached max turns ({max_turns}). Stopping loop.")
                    break

                await asyncio.sleep(0.1)

        except ConversationEnded as e:
            print(f"\n[Orchestrator] Caught ConversationEnded signal.")
        except KeyboardInterrupt:
            print("\n[Orchestrator] Keyboard interrupt detected. Stopping.")
        except Exception as e:
            print(f"\n[Orchestrator] An unexpected error occurred in the main loop: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            print(f"\n--- Main Loop Finished ({target_agent_id}) ---")
