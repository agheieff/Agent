from datetime import datetime
import asyncio
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from Clients import get_llm_client
from Output.output_manager import OutputManager

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

class ToolExtractor:
    @staticmethod
    def extract_tools(response: str) -> List[Tuple[str, Dict[str, str]]]:
        tools = []
        tool_pattern = r'/(\w+)\s*\n((?:[^\n]+\n)+)'
        matches = re.finditer(tool_pattern, response, re.MULTILINE)
        for match in matches:
            tool_name = match.group(1)
            param_block = match.group(2)
            params = {}
            param_lines = param_block.strip().split('\n')
            for line in param_lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    params[key.strip()] = value.strip()
            tools.append((tool_name, params))
        return tools

    @staticmethod
    def extract_thinking(response: str) -> List[str]:
        thinking_pattern = r'\[thinking\](.*?)\[/thinking\]'
        matches = re.finditer(thinking_pattern, response, re.DOTALL)
        return [match.group(1).strip() for match in matches]

    @staticmethod
    def extract_planning(response: str) -> List[str]:
        planning_pattern = r'\[plan\](.*?)\[/plan\]'
        matches = re.finditer(planning_pattern, response, re.DOTALL)
        return [match.group(1).strip() for match in matches]

    @staticmethod
    def is_exit_request(text: str) -> bool:
        exit_patterns = [r'/exit', r'/quit', r'/bye']
        for pattern in exit_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

from Tools.manager import ToolManager

class AutonomousAgent:
    def __init__(
        self,
        api_key: str = "",
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
        self.llm = get_llm_client(self.provider, self.api_key)
        self.should_exit = False
        self.local_conversation_history = []

        self.tool_extractor = ToolExtractor()
        self.tool_manager = ToolManager()
        self.display_manager = OutputManager()

        self.agent_state['status'] = 'ready'

    async def run(self, initial_prompt: str, system_prompt: str = ""):
        try:
            self.agent_state['status'] = 'running'
            self.local_conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ]

            response = await self._generate_response(system_prompt, initial_prompt)
            should_continue = True

            # Introduce an iteration counter; in test mode we only do one iteration.
            iteration = 0

            while should_continue and not self.should_exit:
                response_state = await self._process_response(response)

                if isinstance(response_state, dict) and response_state.get("auto_continue"):
                    response = response_state.get("next_response", "")
                    should_continue = True
                else:
                    should_continue = response_state

                # If running in test mode, only one iteration is performed.
                iteration += 1
                if self.test_mode and iteration >= 1:
                    break

                if should_continue and not self.should_exit:
                    auto_continue = self.config.get("agent", {}).get("autonomous_mode", True)
                    if auto_continue:
                        auto_message = "Continue with your plan based on the tool results."
                        self.local_conversation_history.append({
                            "role": "user",
                            "content": auto_message
                        })
                        response = await self._generate_response(None, auto_message)
                    else:
                        user_input = await self._get_user_input()
                        if user_input.strip().lower() in ["exit", "quit", "bye"]:
                            should_continue = False
                            break
                        response = await self._generate_response(None, user_input)

            self.agent_state['status'] = 'completed'

        except Exception as e:
            logger.error(f"Error in agent run: {e}")
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise

    async def _generate_response(self, system_prompt: Optional[str], user_input: str) -> str:
        try:
            if system_prompt is not None:
                self.local_conversation_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            else:
                self.local_conversation_history.append({
                    "role": "user",
                    "content": user_input
                })

            response = await self.llm.generate_response(self.local_conversation_history)
            self.local_conversation_history.append({
                "role": "assistant",
                "content": response
            })

            print(f"\n{response}\n")
            self.agent_state['last_active'] = datetime.now().isoformat()

            return response

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            error_message = f"I encountered an error while generating a response: {str(e)}"
            self.local_conversation_history.append({
                "role": "assistant",
                "content": error_message
            })
            return error_message

    async def _process_response(self, response: str) -> Any:
        try:
            verbose_level = self.config.get("output", {}).get("verbose_level", 0)

            if self.tool_extractor.is_exit_request(response):
                self.should_exit = True
                return False

            thinking = self.tool_extractor.extract_thinking(response)
            planning = self.tool_extractor.extract_planning(response)

            if verbose_level >= 2:
                if thinking:
                    print(f"[VERBOSE] Extracted {len(thinking)} thinking blocks")
                if planning:
                    print(f"[VERBOSE] Extracted {len(planning)} planning blocks")

            tool_response = await self.tool_manager.process_message(response)

            if tool_response:
                self.agent_state['tools_executed'] += 1
                if verbose_level >= 1:
                    print(f"\n[TOOLS] Executed tools and received response")
                if self.config.get("agent", {}).get("autonomous_mode", True):
                    self.local_conversation_history.append({
                        "role": "user",
                        "content": tool_response
                    })
                    new_response = await self._generate_response(None, tool_response)
                    return {
                        "auto_continue": True,
                        "next_response": new_response
                    }

            return True

        except Exception as e:
            logger.error(f"Error processing response: {e}")
            return True

    async def _get_user_input(self) -> str:
        self.agent_state['status'] = 'waiting_for_input'
        prompt = "\n[User Input] > "
        print(prompt, end="", flush=True)
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input)
        print(f"\n[Input received] Processing...", flush=True)
        self.agent_state['status'] = 'running'
        return user_input
