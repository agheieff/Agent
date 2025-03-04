from datetime import datetime
import asyncio
import logging
import json
import uuid
from typing import Optional, List, Dict, Any, Union, Tuple

from Clients import get_llm_client
from Output.output_manager import OutputManager, output_manager
from Core.parser import ToolParser
from Core.composer import ToolResponseComposer
from Tools.manager import ToolManager

logger = logging.getLogger(__name__)

class ToolResult:
    """
    Class to represent a tool execution result.
    """

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
    """
    Autonomous agent that can reason, plan, and execute tasks.
    """

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

        # Basic agent configuration
        self.api_key = api_key
        self.model_name = model
        self.provider = provider.lower()
        self.test_mode = test_mode
        self.config = config or {}

        # Determine provider type for format handling
        if "claude" in self.model_name.lower() or self.provider == "anthropic":
            self.provider_type = "anthropic"
        elif "deepseek" in self.model_name.lower() or self.provider == "deepseek":
            self.provider_type = "deepseek"
        else:
            self.provider_type = "openai"  # Default

        # Format configuration
        self.default_input_format = self.config.get("format", {}).get("input", "auto")
        self.default_output_format = self.config.get("format", {}).get("output", "json")

        # Agent state
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

        # Components
        self.llm = get_llm_client(self.provider, self.api_key, model=self.model_name)
        self.should_exit = False
        self.local_conversation_history: List[Dict[str, str]] = []
        self.tool_parser = ToolParser()
        self.tool_manager = ToolManager()
        self.response_composer = ToolResponseComposer()
        self.display_manager = output_manager or OutputManager()

        # Set the tool manager's agent context
        self.tool_manager.set_agent_context(self.config, self.llm, self.local_conversation_history)

        # Set default output format
        if self.default_output_format in self.response_composer.composers:
            self.response_composer.set_default_format(self.default_output_format)

        self.agent_state['status'] = 'ready'
        
        # Start time tracking
        self.start_time = datetime.now()
        self.last_compact_time = self.start_time
        self.turn_counter = 0

    async def run(self, initial_prompt: str, system_prompt: str = ""):
        """Run the agent with the given initial prompt."""
        try:
            self.agent_state['status'] = 'running'

            # Initialize conversation history
            self.local_conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ]

            # Generate first response
            response = await self._generate_response(system_prompt, initial_prompt)
            should_continue = True

            # Main agent loop
            iteration = 0
            while should_continue and not self.should_exit:
                # Process the response
                await self._process_response(response)

                iteration += 1
                if self.test_mode and iteration >= 10:  # Limit test mode to 10 iterations
                    break

                # Check if we should continue automatically or get user input
                auto_continue = self.config.get("agent", {}).get("autonomous_mode", True)
                if auto_continue and not self.should_exit:
                    user_followup = "Continue."
                else:
                    user_followup = await self._get_user_input()
                    if user_followup.strip().lower() in ["exit", "quit", "bye"]:
                        break

                # Generate next response
                response = await self._generate_response(None, user_followup)

            self.agent_state['status'] = 'completed'

        except Exception as e:
            logger.error(f"Error in agent run: {e}", exc_info=True)
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise

    async def _generate_response(self, system_prompt: Optional[str], user_input: str) -> Union[str, Dict[str, Any]]:
        """Generate a response from the LLM based on conversation history."""
        try:
            # Update conversation history
            if system_prompt is not None:
                self.local_conversation_history = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ]
            else:
                self.local_conversation_history.append(
                    {"role": "user", "content": user_input}
                )

            # Update turn counter
            self.turn_counter += 1
            
            # Generate response from LLM
            response = await self.llm.generate_response(self.local_conversation_history)

            # Update token usage if available from the LLM client
            if hasattr(self.llm, 'total_tokens'):
                self.tool_manager.update_tokens_used(self.llm.total_tokens)

            # Update conversation history with response
            if isinstance(response, dict):
                # For structured responses, extract the appropriate content
                content = response.get("answer", "") or response.get("content", "")
                self.local_conversation_history.append(
                    {"role": "assistant", "content": content or ""}
                )
            else:
                self.local_conversation_history.append(
                    {"role": "assistant", "content": response or ""}
                )

            logger.debug(f"LLM response: {response}")

            # Update agent state
            self.agent_state['last_active'] = datetime.now().isoformat()
            return response or ""
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            error_message = f"Error generating a response: {str(e)}"
            self.local_conversation_history.append({"role": "assistant", "content": error_message})
            return error_message

    async def _process_response(self, response) -> bool:
        """Process a response from the LLM and execute any tool calls."""
        try:
            # Parse the response based on format
            if isinstance(response, str):
                if not response.strip():
                    return True
                
                # Parse based on provider type
                parsed = self.tool_parser.parse_message(response)
            else:
                # Response is already structured
                parsed = response

            # Extract components from parsed response
            thinking = parsed.get("thinking", "")
            if thinking:
                if output_manager:
                    await output_manager.handle_tool_output("agent_thinking", {
                        "success": True,
                        "output": thinking,
                        "formatter": "agent_thinking"
                    })
                else:
                    print(f"[Agent Thinking]: {thinking}")

            # Extract analysis/reasoning
            analysis = parsed.get("analysis", "") or parsed.get("reasoning", "")
            if analysis:
                if output_manager:
                    await output_manager.handle_tool_output("agent_analysis", {
                        "success": True,
                        "output": analysis,
                        "formatter": "agent_analysis"
                    })
                else:
                    print(f"[Agent Analysis]: {analysis}")

            # Extract final answer
            final_answer = parsed.get("answer", "") or parsed.get("response", "")
            if final_answer:
                if output_manager:
                    await output_manager.handle_tool_output("agent_answer", {
                        "success": True,
                        "output": final_answer,
                        "formatter": "agent_answer"
                    })
                else:
                    print(f"\n[Agent Answer]: {final_answer}\n")

            # Process tool calls
            tool_calls = parsed.get("tool_calls", [])
            
            # Handle DeepSeek format (action/action_input)
            if not tool_calls and "action" in parsed:
                action = parsed.get("action", "")
                action_input = parsed.get("action_input", {}) or parsed.get("parameters", {})
                if action:
                    tool_calls = [{
                        "name": action,
                        "params": action_input
                    }]
            
            # Execute tool calls and get results
            if tool_calls:
                result_str = await self.tool_manager.process_message_from_calls(
                    tool_calls,
                    output_format=self.default_output_format
                )
                if result_str:
                    self.local_conversation_history.append({"role": "user", "content": result_str})
                    
                    # Check for the finish tool to exit
                    for call in tool_calls:
                        if isinstance(call, dict) and call.get("name") == "finish":
                            self.should_exit = True
                            return False

            # Check for exit signal in answer
            if "[EXIT]" in final_answer:
                self.should_exit = True
                return False

            return True
        except Exception as e:
            logger.error(f"Error processing response: {e}", exc_info=True)
            error_message = f"Error processing response: {str(e)}"
            self.local_conversation_history.append({"role": "user", "content": error_message})
            return True  # Continue despite error

    async def _get_user_input(self) -> str:
        """Get input from the user."""
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
