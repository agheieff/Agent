import os
import uuid
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

from Clients import get_llm_client
from Output.output_manager import OutputManager, output_manager
from Core.parser import ToolParser
from Core.composer import ToolResponseComposer
from Tools.manager import ToolManager
from Core.detect_providers import get_active_providers

logger = logging.getLogger(__name__)

class ToolResult:
    def __init__(self, output: str, success: bool, error: str = None):
        self.output = output
        self.success = success
        self.error = error
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'output': self.output,
            'success': self.success,
            'error': self.error,
            'timestamp': self.timestamp.isoformat()
        }

class AutonomousAgent:
    def __init__(
        self,
        api_key: str,
        model: str = "default-model",
        provider: str = "openai",
        test_mode: bool = False,
        config: Dict[str, Any] = None
    ):
        if not api_key:
            raise ValueError("API key required")

        self.api_key = api_key
        self.model_name = model
        self.provider = provider.lower()
        self.test_mode = test_mode
        self.config = config or {}

        active_providers = get_active_providers()
        if self.provider in active_providers:
            self.provider_type = self.provider
            self.api_key = active_providers[self.provider]
        elif active_providers:
            self.provider_type, self.api_key = next(iter(active_providers.items()))
        else:
            self.provider_type = "openai"

        self.default_input_format = self.config.get("format", {}).get("input", "auto")
        self.default_output_format = self.config.get("format", {}).get("output", "json")

        self.agent_id = str(uuid.uuid4())[:8]
        self.agent_state = {
            'started_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'tools_executed': 0,
            'tasks_completed': 0,
            'status': 'initializing',
            'last_error': None,
            'current_task': None,
        }

        self.llm = get_llm_client(self.provider_type, self.api_key, model=self.model_name)
        self.should_exit = False
        self.local_conversation_history: List[Dict[str, str]] = []
        self.tool_parser = ToolParser()
        self.tool_manager = ToolManager()
        self.response_composer = ToolResponseComposer()
        self.display_manager = output_manager or OutputManager()

        self.tool_manager.set_agent_context(self.config, self.llm, self.local_conversation_history)
        if self.default_output_format in self.response_composer.composers:
            self.response_composer.set_default_format(self.default_output_format)

        self.agent_state['status'] = 'ready'
        self.start_time = datetime.now()
        self.last_compact_time = self.start_time
        self.turn_counter = 0

    async def run(self, initial_prompt: str, system_prompt: str = ""):
        try:
            self.agent_state['status'] = 'running'
            self.local_conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ]
            response = await self._generate_response(system_prompt, initial_prompt)
            iteration = 0
            while not self.should_exit:
                await self._process_response(response)
                iteration += 1
                if self.test_mode and iteration >= 10:
                    break
                auto_continue = self.config.get("agent", {}).get("autonomous_mode", True)
                user_followup = "Continue." if auto_continue else await self._get_user_input()
                if user_followup.strip().lower() in ["exit", "quit", "bye"]:
                    break
                response = await self._generate_response(None, user_followup)
            self.agent_state['status'] = 'completed'
        except Exception as e:
            logger.error(f"Error in agent run: {e}", exc_info=True)
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise

    async def _generate_response(self, system_prompt: Optional[str], user_input: str) -> Union[str, Dict[str, Any]]:
        try:
            if system_prompt is not None:
                self.local_conversation_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            else:
                self.local_conversation_history.append({"role": "user", "content": user_input})
            self.turn_counter += 1
            response = await self.llm.generate_response(self.local_conversation_history)
            if hasattr(self.llm, 'total_tokens'):
                self.tool_manager.update_tokens_used(self.llm.total_tokens)
            if isinstance(response, dict):
                content = response.get("answer", "") or response.get("content", "")
                self.local_conversation_history.append({"role": "assistant", "content": content})
            else:
                self.local_conversation_history.append({"role": "assistant", "content": response or ""})
            logger.debug(f"LLM response: {response}")
            self.agent_state['last_active'] = datetime.now().isoformat()
            return response or ""
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            error_message = f"Error generating a response: {str(e)}"
            self.local_conversation_history.append({"role": "assistant", "content": error_message})
            return error_message

    async def _process_response(self, response) -> bool:
        try:
            parsed = self.tool_parser.parse_message(response) if isinstance(response, str) else response

            for key in ("thinking", "analysis", "reasoning"):
                if parsed.get(key):
                    output = {"success": True, "output": parsed[key], "formatter": f"agent_{key}"}
                    if output_manager:
                        await output_manager.handle_tool_output(f"agent_{key}", output)
                    else:
                        print(f"[Agent {key.capitalize()}]: {parsed[key]}")

            final_answer = parsed.get("answer", "") or parsed.get("response", "")
            if final_answer and output_manager:
                await output_manager.handle_tool_output("agent_answer", {
                    "success": True,
                    "output": final_answer,
                    "formatter": "agent_answer"
                })
            elif final_answer:
                print(f"\n[Agent Answer]: {final_answer}\n")

            tool_calls = parsed.get("tool_calls", [])
            if not tool_calls and "action" in parsed:
                action = parsed.get("action", "")
                action_input = parsed.get("action_input", {}) or parsed.get("parameters", {})
                if action:
                    tool_calls = [{"name": action, "params": action_input}]
            if tool_calls:
                result_str = await self.tool_manager.process_message_from_calls(
                    tool_calls, output_format=self.default_output_format
                )
                if result_str:
                    self.local_conversation_history.append({"role": "user", "content": result_str})
                    for call in tool_calls:
                        if isinstance(call, dict) and call.get("name") == "finish":
                            self.should_exit = True
                            return False

            if "[EXIT]" in final_answer:
                self.should_exit = True
                return False

            return True
        except Exception as e:
            logger.error(f"Error processing response: {e}", exc_info=True)
            error_message = f"Error processing response: {str(e)}"
            self.local_conversation_history.append({"role": "user", "content": error_message})
            return True

    async def _get_user_input(self) -> str:
        self.agent_state['status'] = 'waiting_for_input'
        prompt = "\n[User Input] > "
        if output_manager:
            user_input = await output_manager.get_user_input(prompt)
        else:
            print(prompt, end="", flush=True)
            loop = asyncio.get_event_loop()
            user_input = await loop.run_in_executor(None, input)
        self.agent_state['status'] = 'running'
        return user_input
