import asyncio
import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import traceback

# Import configuration helpers
import config as app_config

from Clients.base import BaseClient, ProviderConfig, Message
from Core.agent_config import AgentConfiguration
from Core.agent_instance import AgentInstance, TOOL_EXECUTED_SIGNAL
from Core.executor import Executor
from Tools.error_codes import ConversationEnded, PauseRequested, ErrorCodes
from Prompts.main import build_system_prompt, discover_tools
from Core.utils import get_multiline_input


def load_agent_configurations(config_dir: str = "./AgentConfigs") -> List[AgentConfiguration]:
    # This function remains largely the same, as it loads agent-specific overrides/definitions
    # It doesn't need the detailed provider config from config.py itself.
    config_path = Path(config_dir)
    if not config_path.is_dir():
        print(f"Warning: Configuration directory '{config_dir}' not found.")
        return []

    configs = []
    default_config_data = {}
    default_file = config_path / "default_agent.yaml"

    if default_file.exists():
        try:
            with open(default_file, 'r') as f:
                default_config_data = yaml.safe_load(f) or {}
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
            final_data.update(agent_data) # Override defaults with specific agent data

            # Ensure agent_id is set (from filename if not specified)
            final_data.setdefault('agent_id', file_path.stem)
            # Ensure required fields have defaults if not provided
            final_data.setdefault('role', final_data['agent_id'])
            final_data.setdefault('model_provider', 'anthropic') # Sensible default?
            final_data.setdefault('model_name', app_config.get_provider_config(final_data['model_provider']).default_model if app_config.get_provider_config(final_data['model_provider']) else 'default') # Default model from central config
            final_data.setdefault('system_prompt', f"You are an AI assistant with the role: {final_data['role']}.")
            final_data.setdefault('allowed_tools', [])

            # Ensure allowed_tools is a list, even if null in YAML
            if final_data['allowed_tools'] is None:
                final_data['allowed_tools'] = []

            # Validate provider/model exist in central config
            provider_conf = app_config.get_provider_config(final_data['model_provider'])
            if not provider_conf:
                 print(f"Warning: Provider '{final_data['model_provider']}' defined for agent '{final_data['agent_id']}' not found in config.py. Skipping agent.")
                 continue
            model_conf = app_config.get_model_config(final_data['model_provider'], final_data['model_name'])
            if not model_conf:
                 print(f"Warning: Model '{final_data['model_name']}' for provider '{final_data['model_provider']}' (Agent: '{final_data['agent_id']}') not found in config.py. Using provider default '{provider_conf.default_model}' instead.")
                 final_data['model_name'] = provider_conf.default_model # Fallback to provider default
                 # Double-check default exists
                 if not app_config.get_model_config(final_data['model_provider'], final_data['model_name']):
                     print(f"Error: Default model '{final_data['model_name']}' for provider '{final_data['model_provider']}' also not found. Skipping agent '{final_data['agent_id']}'.")
                     continue


            agent_config_obj = AgentConfiguration(
                agent_id=final_data['agent_id'],
                role=final_data['role'],
                model_provider=final_data['model_provider'],
                model_name=final_data['model_name'], # Use the (potentially corrected) model name
                system_prompt=final_data['system_prompt'],
                allowed_tools=final_data['allowed_tools'],
            )

            configs.append(agent_config_obj)
            print(f"Loaded config for agent: {agent_config_obj.agent_id} (Provider: {agent_config_obj.model_provider}, Model: {agent_config_obj.model_name})")

        except Exception as e:
            print(f"Error loading config file {file_path.name}: {e}")
            traceback.print_exc()

    if not configs:
        raise ValueError("Failed to load any valid agent configurations from YAML files.")

    return configs


class Orchestrator:
    def __init__(self, config_list: List[AgentConfiguration]):
        self.agents: Dict[str, AgentInstance] = {}
        self.clients: Dict[str, BaseClient] = {}
        self.executor = Executor()
        # Discover tools once during initialization
        self.all_discovered_tools = discover_tools()

        self._initialize_clients(config_list)
        self._create_agents(config_list)

    def _initialize_clients(self, config_list: List[AgentConfiguration]):
        """Initializes clients based on providers needed by agent configs."""
        providers_needed = {cfg.model_provider for cfg in config_list}
        print(f"Providers needed based on agent configs: {providers_needed}")

        for provider_name in providers_needed:
            if provider_name in self.clients:
                continue

            # Get provider config from the central config.py
            provider_config = app_config.get_provider_config(provider_name)
            if not provider_config:
                print(f"Warning: Configuration for provider '{provider_name}' not found in config.py. Cannot initialize client.")
                continue

            # Check for API key
            api_key = os.getenv(provider_config.api_key_env)
            if not api_key:
                print(f"Warning: API key env var '{provider_config.api_key_env}' not found for provider '{provider_name}'. Client initialization might fail.")
                # Allow to proceed, BaseClient will raise error if key is truly needed later

            try:
                # Dynamically import the specific client module based on provider name convention
                # (Assumes client file is named like the provider in Clients/API/)
                module_name = f"Clients.API.{provider_name}"
                module = importlib.import_module(module_name)

                client_class = None
                # Find the class inheriting from BaseClient in the imported module
                for name, obj in inspect.getmembers(module):
                    if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient:
                        if client_class is None: # Take the first one found
                            client_class = obj
                        else:
                            print(f"Warning: Multiple BaseClient subclasses found in {module_name}. Using {client_class.__name__}.")
                            break # Stop after finding the first one

                if not client_class:
                    raise ImportError(f"No class inheriting from BaseClient found in module {module_name}")

                # Instantiate the client, passing the loaded ProviderConfig
                client_instance = client_class(config=provider_config)
                self.clients[provider_name] = client_instance
                print(f"Initialized client for: {provider_name}")

            except (ImportError, AttributeError, ValueError, Exception) as e:
                print(f"Error initializing client for provider '{provider_name}': {e}")
                traceback.print_exc() # Print stack trace for debugging initialization errors


    def _create_agents(self, config_list: List[AgentConfiguration]):
        """Creates AgentInstance objects from configurations."""
        if not self.all_discovered_tools:
             print("Warning: Tool discovery yielded no tools.")

        for agent_config in config_list:
            if agent_config.agent_id in self.agents:
                print(f"Warning: Duplicate agent_id '{agent_config.agent_id}'. Skipping.")
                continue

            client = self.clients.get(agent_config.model_provider)
            if not client:
                print(f"Warning: Client for provider '{agent_config.model_provider}' not initialized for agent '{agent_config.agent_id}'. Skipping agent creation.")
                continue

            try:
                # Pass the agent-specific config, the initialized client, executor, and discovered tools
                agent_instance = AgentInstance(
                    config=agent_config,
                    client=client,
                    executor=self.executor,
                    all_discovered_tools=self.all_discovered_tools
                )
                self.agents[agent_config.agent_id] = agent_instance

            except Exception as e:
                print(f"Error creating agent instance '{agent_config.agent_id}': {e}")
                traceback.print_exc()

    async def run_main_loop(self, initial_prompt: str, target_agent_id: str = "ceo", max_turns: int = 10):
        # This function remains the same as the previous version with the SYSTEM REMINDER logic
        agent = self.agents.get(target_agent_id)
        if not agent:
            print(f"Error: Target agent '{target_agent_id}' not found.")
            print(f"Available agents: {list(self.agents.keys())}")
            return

        # Store the initial prompt for potential reminders
        _initial_user_prompt = initial_prompt
        agent.add_message('user', _initial_user_prompt)
        print(f"\nUser (to {target_agent_id}): {_initial_user_prompt}")

        turn_count = 0
        while turn_count < max_turns:
            try:
                print(f"\n--- Turn {turn_count + 1}/{max_turns} ({target_agent_id}) ---")

                # --- Determine if "Proceed." should potentially be added LATER ---
                should_add_proceed_later = False
                if agent.messages:
                    potential_last_assistant_msg_index = -1
                    if agent.messages[-1].role == 'user' and agent.messages[-1].content.startswith("[SYSTEM REMINDER]"):
                        if len(agent.messages) > 1:
                           potential_last_assistant_msg_index = -2
                    else:
                        potential_last_assistant_msg_index = -1

                    if potential_last_assistant_msg_index < 0 and len(agent.messages) > abs(potential_last_assistant_msg_index):
                        last_msg = agent.messages[potential_last_assistant_msg_index]
                        if last_msg.role == 'assistant' and not last_msg.content.startswith(("Tool '", "[Tool Result", "@result", "!!! IMPORTANT", "✓ CONVERSATION ENDED", "✗ CONVERSATION ENDED", "⚠ CONVERSATION ENDED")):
                            if not (len(agent.messages) > 1 and agent.messages[-2].role == 'user' and agent.messages[-2].content == "Proceed."):
                                should_add_proceed_later = True

                # --- Execute the agent's turn ---
                result = await agent.execute_turn()
                turn_count += 1

                # --- Handle results and inject reminder if necessary ---
                reminder_added_this_turn = False
                if result is TOOL_EXECUTED_SIGNAL:
                    print("[Orchestrator] Non-pausing tool executed.")
                    # --- ADD REMINDER ---
                    last_real_user_prompt = _initial_user_prompt
                    for i in range(len(agent.messages) - 1, -1, -1):
                         msg = agent.messages[i]
                         if msg.role == 'user' and not msg.content.startswith(("Proceed.", "[SYSTEM REMINDER]")):
                              last_real_user_prompt = msg.content
                              break
                    reminder_text = f"[SYSTEM REMINDER] Previous step completed. Recall the goal: \"{last_real_user_prompt[:100].strip()}...\" Now execute the *next* step based on your plan."
                    agent.add_message('user', reminder_text)
                    print(f"User: {reminder_text}")
                    reminder_added_this_turn = True
                    # --- END REMINDER ---
                    pass

                elif isinstance(result, str) and result.startswith("[ERROR:"):
                    print(f"\n[Orchestrator] Agent '{target_agent_id}' reported error: {result}. Stopping loop.")
                    break
                elif isinstance(result, str):
                    pass
                elif result is None:
                     print(f"\n[Orchestrator] Agent '{target_agent_id}' returned None unexpectedly. Stopping loop.")
                     break

                # --- Add "Proceed." ONLY if needed AND turn didn't run a tool AND no reminder was just added ---
                if should_add_proceed_later and result is not TOOL_EXECUTED_SIGNAL and not reminder_added_this_turn:
                    if not (agent.messages and agent.messages[-1].role == 'user' and agent.messages[-1].content == "Proceed."):
                        agent.add_message('user', "Proceed.")
                        print("User: Proceed.")

            # --- Handle control flow exceptions ---
            except PauseRequested as pr:
                print("\n-----------------------------------------------------")
                print(f"[Orchestrator] {pr.message}")
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
                    agent.add_message('user', "Proceed.")
                    print("User: Proceed.")
                continue

            except ConversationEnded as ce:
                print(f"\n[Orchestrator] Caught ConversationEnded signal: {ce}")
                break

            except KeyboardInterrupt:
                print("\n[Orchestrator] Keyboard interrupt detected. Stopping.")
                break

            except Exception as e:
                print(f"\n[Orchestrator] An unexpected error occurred in the main loop: {type(e).__name__}: {e}")
                traceback.print_exc()
                break

            # --- Max turns check ---
            if turn_count >= max_turns:
                print(f"\n[Orchestrator] Reached max turns ({max_turns}). Stopping loop.")
                break

            await asyncio.sleep(0.1)

        print(f"\n--- Main Loop Finished ({target_agent_id}) ---")
