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
from Core.detect_providers import get_active_providers

logger = logging.getLogger(__name__)

class ToolResult:
    def __init__(self, output: str, success: bool, error: str = None):
        self.output = output
        self.success = success
        self.error = error
        self.timestamp = datetime.now()
    def to_dict(self) -> Dict[str, Any]:
        return {"output": self.output, "success": self.success, "error": self.error, "timestamp": self.timestamp.isoformat()}

class AutonomousAgent:
    def __init__(self, api_key: str, model: str = "default-model", provider: str = "openai", test_mode: bool = False, config: Dict[str, Any] = None):
        if not api_key:
            raise ValueError("API key required")
        self.api_key = api_key
        self.model_name = model
        self.provider = provider.lower()
        self.test_mode = test_mode
        self.config = config or {}
        a = get_active_providers()
        if self.provider in a:
            self.provider_type = self.provider
            self.api_key = a[self.provider]
        elif a:
            self.provider_type, listkey = next(iter(a.items()))
            self.api_key = listkey
        else:
            self.provider_type = "openai"
        self.default_input_format = self.config.get("format", {}).get("input", "auto")
        self.default_output_format = self.config.get("format", {}).get("output", "json")
        self.agent_id = str(uuid.uuid4())[:8]
        self.agent_state = {
            "started_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "tools_executed": 0,
            "tasks_completed": 0,
            "status": "initializing",
            "last_error": None,
            "current_task": None
        }
        self.llm = get_llm_client(self.provider_type, self.api_key, model=self.model_name)
        self.should_exit = False
        self.local_conversation_history: List[Dict[str, str]] = []
        self.tool_parser = ToolParser()
        self.response_composer = ToolResponseComposer()
        self.display_manager = output_manager or OutputManager()
        if self.default_output_format in self.response_composer.composers:
            self.response_composer.set_default_format(self.default_output_format)
        self.agent_state["status"] = "ready"
        self.start_time = datetime.now()
        self.last_compact_time = self.start_time
        self.turn_counter = 0

    async def run(self, initial_prompt: str, system_prompt: str = ""):
        try:
            self.agent_state["status"] = "running"
            self.local_conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ]
            r = await self._generate_response(system_prompt, initial_prompt)
            it = 0
            while not self.should_exit:
                await self._process_response(r)
                it += 1
                if self.test_mode and it >= 10:
                    break
                a = self.config.get("agent", {}).get("autonomous_mode", True)
                u = "Continue." if a else await self._get_user_input()
                if u.strip().lower() in ["exit", "quit", "bye"]:
                    break
                r = await self._generate_response(None, u)
            self.agent_state["status"] = "completed"
        except Exception as e:
            logger.error(f"Error in agent run: {e}", exc_info=True)
            self.agent_state["status"] = "error"
            self.agent_state["last_error"] = str(e)
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
            r = await self.llm.generate_response(self.local_conversation_history)
            if isinstance(r, dict):
                c = r.get("answer", "") or r.get("content", "")
                self.local_conversation_history.append({"role": "assistant", "content": c})
            else:
                self.local_conversation_history.append({"role": "assistant", "content": r or ""})
            logger.debug(f"LLM response: {r}")
            self.agent_state["last_active"] = datetime.now().isoformat()
            return r or ""
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            em = f"Error generating a response: {str(e)}"
            self.local_conversation_history.append({"role": "assistant", "content": em})
            return em

    async def _process_response(self, response) -> bool:
        try:
            # Convert to string if not already
            p = response if isinstance(response, str) else json.dumps(response)
            # Parse the response
            d = self.tool_parser.parse_message(p)
            
            # Handle thinking, analysis, reasoning sections
            for k in ("thinking", "analysis", "reasoning"):
                if v := d.get(k):
                    o = {"success": True, "output": v, "formatter": f"agent_{k}"}
                    if output_manager:
                        await output_manager.handle_tool_output(f"agent_{k}", o)
                    else:
                        print(f"[Agent {k.capitalize()}]: {v}")
            
            # Handle answer/response
            if a := (d.get("answer") or d.get("response", "")):
                if output_manager:
                    await output_manager.handle_tool_output("agent_answer", {"success": True, "output": a, "formatter": "agent_answer"})
                else:
                    print(f"\n[Agent Answer]: {a}\n")
                    
                if "[EXIT]" in a:
                    self.should_exit = True
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Error processing response: {e}", exc_info=True)
            self.local_conversation_history.append({"role": "user", "content": f"Error processing response: {str(e)}"})
            return True

    async def _get_user_input(self) -> str:
        self.agent_state["status"] = "waiting_for_input"
        p = "\n[User Input] > "
        if output_manager:
            i = await output_manager.get_user_input(p)
        else:
            print(p, end="", flush=True)
            loop = asyncio.get_event_loop()
            i = await loop.run_in_executor(None, input)
        self.agent_state["status"] = "running"
        return i
