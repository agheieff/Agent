import asyncio
import importlib
import inspect
import os
from pathlib import Path
from typing import Dict, List, Optional
import yaml
import traceback

from Clients.base import BaseClient, ProviderConfig, Message # Import Message
from Core.agent_config import AgentConfiguration
# Import the signal from agent_instance
from Core.agent_instance import AgentInstance, TOOL_EXECUTED_SIGNAL
from Core.executor import Executor
# Import exceptions
from Tools.error_codes import ConversationEnded, PauseRequested, ErrorCodes
from Prompts.main import build_system_prompt, discover_tools
from Core.utils import get_multiline_input


def load_agent_configurations(config_dir: str = "./AgentConfigs") -> List[AgentConfiguration]:
    # ... (function remains the same) ...
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
            final_data.update(agent_data)

            if 'agent_id' not in final_data:
                final_data['agent_id'] = file_path.stem

            final_data.setdefault('role', final_data['agent_id'])
            final_data.setdefault('model_provider', 'deepseek') # Consider making this truly default
            final_data.setdefault('model_name', 'deepseek-chat') # Consider making this truly default
            final_data.setdefault('system_prompt', f"You are an AI assistant with the role: {final_data['role']}.")
            final_data.setdefault('allowed_tools', [])

            # Ensure allowed_tools is a list, even if null in YAML
            if final_data['allowed_tools'] is None:
                final_data['allowed_tools'] = []

            config = AgentConfiguration(
                agent_id=final_data['agent_id'],
                role=final_data['role'],
                model_provider=final_data['model_provider'],
                model_name=final_data['model_name'],
                system_prompt=final_data['system_prompt'],
                allowed_tools=final_data['allowed_tools'],
            )

            configs.append(config)
            print(f"Loaded config for agent: {config.agent_id} (Provider: {config.model_provider}, Model: {config.model_name})")

        except Exception as e:
            print(f"Error loading config file {file_path.name}: {e}")
            traceback.print_exc()

    if not configs:
        # Check if only default exists, maybe load it as a fallback?
        if default_config_data and 'agent_id' in default_config_data:
            print("Warning: No specific agent YAMLs found, attempting to load default_agent.yaml as the only agent.")
            # (Add logic similar to above to create AgentConfiguration from default_config_data)
            # For now, raise error if truly empty.
            pass
        else:
            raise ValueError("Failed to load any valid agent configurations.")

    return configs


class Orchestrator:
    def __init__(self, config_list: List[AgentConfiguration]):
        self.agents: Dict[str, AgentInstance] = {}
        self.clients: Dict[str, BaseClient] = {}
        self.executor = Executor()
        self.all_discovered_tools = self.executor.tools # Get tools directly from initialized Executor

        self._initialize_clients(config_list)
        self._create_agents(config_list)

    def _initialize_clients(self, config_list: List[AgentConfiguration]):
        # ... (function remains the same) ...
        providers_needed = {cfg.model_provider for cfg in config_list}

        for provider_name in providers_needed:
            if provider_name in self.clients:
                continue

            try:
                # Load the module dynamically
                module_name = f"Clients.API.{provider_name}"
                module = importlib.import_module(module_name)

                client_class = None
                provider_config = None
                config_const_name = f"{provider_name.upper()}_CONFIG"

                # --- Find the Client class and Config more robustly ---
                for name, obj in inspect.getmembers(module):
                    # Find class inheriting from BaseClient (but not BaseClient itself)
                    if inspect.isclass(obj) and issubclass(obj, BaseClient) and obj is not BaseClient:
                        if client_class is None: # Take the first one found
                            client_class = obj
                        else:
                            # Handle case where multiple client classes might be defined (unlikely but possible)
                            print(f"Warning: Multiple BaseClient subclasses found in {module_name}. Using {client_class.__name__}.")
                    # Find ProviderConfig instance matching the provider name
                    elif isinstance(obj, ProviderConfig) and obj.name == provider_name:
                            provider_config = obj
                    # Fallback: Find ProviderConfig instance by constant naming convention
                    elif name == config_const_name and isinstance(obj, ProviderConfig):
                            if provider_config is None: # Only use if not already found by name match
                                provider_config = obj
                # --- End of robust finding logic ---

                if not client_class:
                    # Raise error if no suitable class was found
                    raise ValueError(f"No class inheriting from BaseClient found in {module_name}")
                if not provider_config:
                    # Raise error if no suitable config was found
                    raise ValueError(f"ProviderConfig instance for '{provider_name}' not found in {module_name}")


                api_key = os.getenv(provider_config.api_key_env)
                if not api_key:
                    # Allow initialization without key for now, BaseClient handles error later if needed
                    print(f"Warning: API key env var '{provider_config.api_key_env}' not found for provider '{provider_name}'. Client might fail if used.")

                # Instantiate client - pass config if constructor accepts it
                sig = inspect.signature(client_class.__init__)
                if 'config' in sig.parameters:
                    client_instance = client_class(config=provider_config)
                else:
                    # Fallback for clients that don't take config in __init__
                    client_instance = client_class()
                    # Manually set config if possible, though BaseClient usually does this
                    if hasattr(client_instance, 'config') and client_instance.config is None:
                            client_instance.config = provider_config
                            # Re-initialize if necessary after setting config, if the client supports it
                            if hasattr(client_instance, '_initialize'):
                                client_instance._initialize()

                self.clients[provider_name] = client_instance
                print(f"Initialized client for: {provider_name}")

            except (ImportError, AttributeError, ValueError, Exception) as e:
                print(f"Error initializing client for provider '{provider_name}': {e}")
                traceback.print_exc() # Print stack trace for debugging initialization errors


    def _create_agents(self, config_list: List[AgentConfiguration]):
        # ... (function remains the same) ...
        for config in config_list:
            if config.agent_id in self.agents:
                print(f"Warning: Duplicate agent_id '{config.agent_id}'. Skipping.")
                continue

            client = self.clients.get(config.model_provider)
            if not client:
                print(f"Warning: Client for provider '{config.model_provider}' not initialized or failed to initialize. Cannot create agent '{config.agent_id}'.")
                continue

            try:
                # Pass the already discovered tools
                agent_instance = AgentInstance(config, client, self.executor, self.all_discovered_tools)
                self.agents[config.agent_id] = agent_instance

            except Exception as e:
                print(f"Error creating agent '{config.agent_id}': {e}")
                traceback.print_exc()


    async def run_main_loop(self, initial_prompt: str, target_agent_id: str = "ceo", max_turns: int = 10):
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
                # This checks if the *previous* turn ended with a simple assistant text response
                should_add_proceed_later = False
                if agent.messages:
                    # Check message before the last one (if it exists)
                    # Because the last one might now be the reminder we add after a tool call
                    potential_last_assistant_msg_index = -1
                    if agent.messages[-1].role == 'user' and agent.messages[-1].content.startswith("[SYSTEM REMINDER]"):
                        if len(agent.messages) > 1:
                           potential_last_assistant_msg_index = -2
                    else:
                        potential_last_assistant_msg_index = -1

                    if potential_last_assistant_msg_index < 0 and len(agent.messages) > abs(potential_last_assistant_msg_index):
                        last_msg = agent.messages[potential_last_assistant_msg_index]
                        # Condition: The message was from assistant AND it wasn't a tool result/special message
                        if last_msg.role == 'assistant' and not last_msg.content.startswith(("Tool '", "[Tool Result", "@result", "!!! IMPORTANT", "✓ CONVERSATION ENDED", "✗ CONVERSATION ENDED", "⚠ CONVERSATION ENDED")):
                            # Avoid adding Proceed. after Proceed.
                            if not (len(agent.messages) > 1 and agent.messages[-2].role == 'user' and agent.messages[-2].content == "Proceed."):
                                should_add_proceed_later = True # Mark potential need

                # --- Execute the agent's turn ---
                result = await agent.execute_turn()
                turn_count += 1

                # --- Handle results and inject reminder if necessary ---
                reminder_added_this_turn = False
                if result is TOOL_EXECUTED_SIGNAL:
                    print("[Orchestrator] Non-pausing tool executed.")
                    # --- ADD REMINDER ---
                    # Find the last *actual* user message (not 'Proceed.' or reminder)
                    last_real_user_prompt = _initial_user_prompt # Default to initial
                    for i in range(len(agent.messages) - 1, -1, -1):
                         msg = agent.messages[i]
                         # Look for user messages that are not Proceed or our own reminder
                         if msg.role == 'user' and not msg.content.startswith(("Proceed.", "[SYSTEM REMINDER]")):
                              last_real_user_prompt = msg.content
                              break
                    # Construct a concise reminder
                    reminder_text = f"[SYSTEM REMINDER] Previous step completed. Recall the goal: \"{last_real_user_prompt[:100].strip()}...\" Now execute the *next* step based on your plan."
                    agent.add_message('user', reminder_text) # Add as user message to force attention
                    print(f"User: {reminder_text}") # Make reminder visible
                    reminder_added_this_turn = True
                    # --- END REMINDER ---
                    pass # Continue loop

                elif isinstance(result, str) and result.startswith("[ERROR:"):
                    print(f"\n[Orchestrator] Agent '{target_agent_id}' reported error: {result}. Stopping loop.")
                    break
                elif isinstance(result, str):
                    # Agent returned text without tool call/error
                    pass # Loop continues naturally
                elif result is None:
                     print(f"\n[Orchestrator] Agent '{target_agent_id}' returned None unexpectedly. Stopping loop.")
                     break


                # --- Add "Proceed." ONLY if needed AND turn didn't run a tool AND no reminder was just added ---
                if should_add_proceed_later and result is not TOOL_EXECUTED_SIGNAL and not reminder_added_this_turn:
                    # Ensure we don't add "Proceed." if the last message IS ALREADY "Proceed."
                    # (This check might be redundant due to AgentInstance.add_message, but good for safety)
                    if not (agent.messages and agent.messages[-1].role == 'user' and agent.messages[-1].content == "Proceed."):
                        agent.add_message('user', "Proceed.")
                        print("User: Proceed.")

            # --- Handle control flow exceptions ---
            except PauseRequested as pr:
                print("\n-----------------------------------------------------")
                print(f"[Orchestrator] {pr.message}") # Use message directly from exception
                print("-----------------------------------------------------")

                user_input = get_multiline_input("> ")
                if user_input is None: # Handle Ctrl+D or EOF
                    print("\nExiting loop due to user input (EOF).")
                    break
                elif user_input.strip():
                    print(f"User (to {target_agent_id}): {user_input}")
                    agent.add_message('user', user_input)
                else:
                    print("[Empty input received. Resuming autonomous run...]")
                    # Explicitly add Proceed if user just hits Enter after a pause
                    agent.add_message('user', "Proceed.")
                    print("User: Proceed.")
                # Don't break, continue the loop to process next turn or user input
                continue

            except ConversationEnded as ce:
                print(f"\n[Orchestrator] Caught ConversationEnded signal: {ce}")
                break # Exit the main loop

            except KeyboardInterrupt:
                print("\n[Orchestrator] Keyboard interrupt detected. Stopping.")
                break # Exit the main loop

            except Exception as e:
                print(f"\n[Orchestrator] An unexpected error occurred in the main loop: {type(e).__name__}: {e}")
                traceback.print_exc()
                break # Exit on unexpected errors

            # --- Max turns check ---
            if turn_count >= max_turns:
                print(f"\n[Orchestrator] Reached max turns ({max_turns}). Stopping loop.")
                break

            await asyncio.sleep(0.1) # Small delay between turns

        print(f"\n--- Main Loop Finished ({target_agent_id}) ---")
