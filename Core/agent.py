from datetime import datetime
import asyncio
import logging
import uuid
from typing import Optional, List, Dict, Any

from Clients import get_llm_client
from Output.output_manager import OutputManager
from Core.parser import ToolParser
from Tools.manager import ToolManager

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
        self.llm = get_llm_client(self.provider, self.api_key, model=self.model_name)
        self.should_exit = False

        self.local_conversation_history: List[Dict[str, str]] = []
        self.tool_manager = ToolManager()
        self.display_manager = OutputManager()

        self.agent_state['status'] = 'ready'

    async def run(self, initial_prompt: str, system_prompt: str = ""):
        try:
            self.agent_state['status'] = 'running'
            # Start conversation with system + user messages
            self.local_conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ]

            response = await self._generate_response(system_prompt, initial_prompt)
            should_continue = True

            iteration = 0
            while should_continue and not self.should_exit:
                response_state = await self._process_response(response)
                # If test mode, break after first iteration
                iteration += 1
                if self.test_mode and iteration >= 1:
                    break

                if response_state == False or self.should_exit:
                    should_continue = False
                    break

                # In fully-autonomous mode, continue automatically:
                auto_continue = self.config.get("agent", {}).get("autonomous_mode", True)
                if auto_continue and not self.should_exit:
                    user_followup = "Continue."  # could be "Ok, next step" or some other auto prompt
                else:
                    # If not autonomous, ask user for next input:
                    user_followup = await self._get_user_input()
                    if user_followup.strip().lower() in ["exit", "quit", "bye"]:
                        break

                response = await self._generate_response(None, user_followup)

            self.agent_state['status'] = 'completed'

        except Exception as e:
            logger.error(f"Error in agent run: {e}", exc_info=True)
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise

    async def _generate_response(self, system_prompt: Optional[str], user_input: str) -> str:
        """
        Send conversation history to LLM and get the assistant response.
        """
        try:
            if system_prompt is not None:
                # Reset conversation:
                self.local_conversation_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            else:
                self.local_conversation_history.append(
                    {"role": "user", "content": user_input}
                )

            response = await self.llm.generate_response(self.local_conversation_history)
            self.local_conversation_history.append(
                {"role": "assistant", "content": response or ""}
            )
            logger.debug(f"LLM response: {response}")

            self.agent_state['last_active'] = datetime.now().isoformat()
            return response or ""

        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            error_message = f"Error generating a response: {str(e)}"
            self.local_conversation_history.append({"role": "assistant", "content": error_message})
            return error_message

    async def _process_response(self, response: str) -> bool:
        """
        Parse the LLM's response as JSON, execute any tool calls, and store final answer.
        Return True if we should continue, False to stop.
        """
        if not response.strip():
            return True

        parsed = ToolParser.parse_message(response)

        # If there's an "answer" field, we can display it:
        final_answer = parsed.get("answer", "")
        if final_answer:
            print(f"\n[Agent Answer]: {final_answer}\n")

        # If there are tool calls, execute them:
        tool_calls = parsed.get("tool_calls", [])
        if tool_calls:
            result_str = await self.tool_manager.process_message_from_calls(tool_calls)
            # Optionally, we can inject result_str back into conversation or keep it quiet
            if result_str:
                # In some designs, we might re-inject the tool results as user content:
                self.local_conversation_history.append({"role": "user", "content": result_str})

        # Check if the agent wants to exit (some final condition):
        # e.g. If final_answer includes "goodbye" or something
        # For demonstration, let's check a special token:
        if "[EXIT]" in final_answer:
            return False

        return True

    async def _get_user_input(self) -> str:
        """
        For non-autonomous mode, request user input from console.
        """
        self.agent_state['status'] = 'waiting_for_input'
        prompt = "\n[User Input] > "
        print(prompt, end="", flush=True)
        loop = asyncio.get_event_loop()
        user_input = await loop.run_in_executor(None, input)
        self.agent_state['status'] = 'running'
        return user_input
