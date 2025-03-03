import asyncio
import logging
import os
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from Clients.LLM import get_llm_client
from Memory.Manager.memory_manager import MemoryManager
from Memory.Cache.memory_cache import MemoryCache
from Memory.Hierarchy.memory_hierarchy import MemoryHierarchy
from Memory.Preloader.memory_preloader import MemoryPreloader
from Tools.System.shell_adapter import ShellAdapter
from Tools.File.file_operations import FileOperations
from Tools.Search.search_tools import SearchTools
from Tools.Package.package_manager import PackageManager
from Core.task_manager import TaskManager
from Core.session_manager import SessionManager
from Output.display_manager import DisplayManager

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
    """
    Extracts tool calls from LLM responses.
    Tool format: /tool_name\nparam1: value1\nparam2: value2
    """

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

class ToolRegistry:
    """Manages available tools and their execution"""
    def __init__(self):
        self.tools = {}
        self.file_ops = FileOperations()
        self.search_tools = SearchTools()
        self.package_manager = PackageManager()

    def register_tool(self, name: str, handler_func):
        self.tools[name] = handler_func

    def setup_default_tools(self):
        self.register_tool("view_file", self.view_file)
        self.register_tool("edit_file", self.edit_file)
        self.register_tool("replace_file", self.replace_file)
        self.register_tool("search_files", self.search_files)
        self.register_tool("find_text", self.find_text)
        self.register_tool("list_dir", self.list_dir)
        self.register_tool("install_package", self.install_package)

    async def execute_tool(self, tool_name: str, params: Dict[str, str]) -> ToolResult:
        if tool_name not in self.tools:
            return ToolResult(
                output="",
                success=False,
                error=f"Unknown tool: {tool_name}"
            )

        try:
            return await self.tools[tool_name](params)
        except Exception as e:
            return ToolResult(
                output="",
                success=False,
                error=f"Error executing {tool_name}: {str(e)}"
            )

    async def view_file(self, params: Dict[str, str]) -> ToolResult:
        file_path = params.get("path")
        if not file_path:
            return ToolResult("", False, "Missing 'path' parameter")

        offset = int(params.get("offset", "0"))
        limit = int(params.get("limit", "2000"))

        try:
            content = self.file_ops.view(file_path, offset, limit)
            return ToolResult(content, True)
        except Exception as e:
            return ToolResult("", False, str(e))

    async def edit_file(self, params: Dict[str, str]) -> ToolResult:
        file_path = params.get("path")
        old_string = params.get("old")
        new_string = params.get("new")

        if not all([file_path, old_string, new_string]):
            return ToolResult("", False, "Missing required parameters (path, old, new)")

        try:
            result = self.file_ops.edit(file_path, old_string, new_string)
            return ToolResult(result, True)
        except Exception as e:
            return ToolResult("", False, str(e))

    async def replace_file(self, params: Dict[str, str]) -> ToolResult:
        file_path = params.get("path")
        content = params.get("content")

        if not all([file_path, content]):
            return ToolResult("", False, "Missing required parameters (path, content)")

        try:
            result = self.file_ops.replace(file_path, content)
            return ToolResult(result, True)
        except Exception as e:
            return ToolResult("", False, str(e))

    async def search_files(self, params: Dict[str, str]) -> ToolResult:
        pattern = params.get("pattern")
        path = params.get("path", ".")

        if not pattern:
            return ToolResult("", False, "Missing 'pattern' parameter")

        try:
            results = self.search_tools.glob_tool(pattern, path)
            return ToolResult(json.dumps(results, indent=2), True)
        except Exception as e:
            return ToolResult("", False, str(e))

    async def find_text(self, params: Dict[str, str]) -> ToolResult:
        pattern = params.get("pattern")
        include = params.get("include")
        path = params.get("path", ".")

        if not pattern:
            return ToolResult("", False, "Missing 'pattern' parameter")

        try:
            results = self.search_tools.grep_tool(pattern, include, path)
            return ToolResult(json.dumps(results, indent=2), True)
        except Exception as e:
            return ToolResult("", False, str(e))

    async def list_dir(self, params: Dict[str, str]) -> ToolResult:
        path = params.get("path", ".")
        hide_hidden = params.get("hide_hidden", "false").lower() in ["true", "yes", "1"]

        try:
            results = self.search_tools.ls(path, hide_hidden)
            return ToolResult(json.dumps(results, indent=2), True)
        except Exception as e:
            return ToolResult("", False, str(e))

    async def install_package(self, params: Dict[str, str]) -> ToolResult:
        package = params.get("name")
        package_type = params.get("type", "python")
        version = params.get("version")

        if not package:
            return ToolResult("", False, "Missing 'name' parameter")

        try:
            if package_type == "python":
                result = await self.package_manager.install_python_package(package, version)
            elif package_type == "npm":
                result = await self.package_manager.install_npm_package(package, version)
            elif package_type == "system":
                result = await self.package_manager.install_system_package(package)
            else:
                return ToolResult("", False, f"Unsupported package type: {package_type}")

            return ToolResult(result, True)
        except Exception as e:
            return ToolResult("", False, str(e))

class AutonomousAgent:
    def __init__(
        self,
        memory_manager: MemoryManager = None,
        session_manager: SessionManager = None,
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
        self.memory_manager = memory_manager or MemoryManager()
        self.memory_path = self.memory_manager.base_path
        self.session_manager = session_manager or SessionManager(self.memory_path, self.memory_manager)
        self.task_manager = TaskManager(self.memory_path)
        self.display_manager = DisplayManager()

        self._setup_storage()
        self.tool_registry = ToolRegistry()
        self.tool_registry.setup_default_tools()
        self.tool_extractor = ToolExtractor()

    def _setup_storage(self):
        for directory in ["tasks", "reflections", "notes", "working_memory", "temporal"]:
            dir_path = self.memory_path / directory
            dir_path.mkdir(exist_ok=True, parents=True)

        self.agent_id = str(uuid.uuid4())[:8]
        self.agent_state = {
            'started_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'tools_executed': 0,
            'tasks_completed': 0,
            'memory_operations': 0,
            'status': 'initializing',
            'last_error': None,
            'current_task': None,
        }

        self.reflections = []
        self.planned_steps = []
        self.llm = get_llm_client(self.provider, self.api_key)
        self.current_conversation_id = None
        self.should_exit = False
        self.local_conversation_history = []
        self.working_memory = {}
        self.agent_state['status'] = 'ready'

    async def run(self, initial_prompt: str, system_prompt: str = ""):
        try:
            self.agent_state['status'] = 'running'
            self.current_conversation_id = f"session_{int(time.time())}"

            self.local_conversation_history = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": initial_prompt}
            ]

            response = await self._generate_response(system_prompt, initial_prompt)
            should_continue = True

            while should_continue and not self.should_exit:
                self.memory_manager.update_conversation_metrics(increment_turns=True)

                response_state = await self._process_response(response)

                if isinstance(response_state, dict) and response_state.get("auto_continue"):
                    response = response_state.get("next_response", "")
                    should_continue = True
                else:
                    should_continue = response_state

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

            await self._save_session_summary()
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

    async def _process_response(self, response: str) -> bool:
        try:
            verbose_level = self.config.get("output", {}).get("verbose_level", 0)

            tools = self.tool_extractor.extract_tools(response)

            if self.tool_extractor.is_exit_request(response):
                self.should_exit = True
                return False

            thinking = self.tool_extractor.extract_thinking(response)
            planning = self.tool_extractor.extract_planning(response)

            if verbose_level >= 2:
                if tools:
                    print(f"\n[VERBOSE] Extracted {len(tools)} tools")
                if thinking:
                    print(f"[VERBOSE] Extracted {len(thinking)} thinking blocks")
                if planning:
                    print(f"[VERBOSE] Extracted {len(planning)} planning blocks")

            tool_results = []

            for tool_name, params in tools:
                if verbose_level >= 1:
                    param_preview = ", ".join([f"{k}: {v[:20]}..." if len(v) > 20 else f"{k}: {v}" 
                                             for k, v in params.items()])
                    print(f"> Tool: {tool_name}({param_preview})")

                result = await self.tool_registry.execute_tool(tool_name, params)

                if result.success:
                    print(f"✅ Tool {tool_name} executed successfully")
                    if verbose_level >= 2:
                        print(f"  Result: {result.output[:100]}{'...' if len(result.output) > 100 else ''}")
                else:
                    print(f"❌ Tool {tool_name} failed: {result.error}")

                tool_results.append({
                    "tool": tool_name,
                    "params": params,
                    "result": result.to_dict()
                })

                self.agent_state['tools_executed'] += 1

            if tool_results and self.config.get("agent", {}).get("autonomous_mode", True):
                results_summary = "\n\nI've executed these tools with the following results:\n"

                for result in tool_results:
                    tool_name = result["tool"]
                    success = result["result"]["success"]
                    output_preview = result["result"]["output"]
                    if len(output_preview) > 100:
                        output_preview = output_preview[:97] + "..."

                    status = "✓" if success else "✗"
                    error = result["result"].get("error", "")

                    if success:
                        results_summary += f"- {tool_name}: {status} {output_preview}\n"
                    else:
                        results_summary += f"- {tool_name}: {status} Error: {error}\n"

                results_summary += "\nPlease continue with your plan based on these results."

                self.local_conversation_history.append({
                    "role": "user",
                    "content": results_summary
                })

                new_response = await self._generate_response(None, results_summary)

                return {
                    "auto_continue": True,
                    "next_response": new_response
                }

            if self.memory_manager and self.current_conversation_id:
                self.memory_manager.save_conversation(
                    self.current_conversation_id,
                    self.local_conversation_history,
                    metadata={
                        "tools_executed": self.agent_state['tools_executed'],
                        "status": self.agent_state['status'],
                        "timestamp": time.time()
                    }
                )

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

    async def _save_session_summary(self) -> None:
        try:
            summary_path = self.memory_path / "summaries"
            summary_path.mkdir(exist_ok=True, parents=True)

            summary = f"Session Summary ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n"
            summary += "=" * 50 + "\n\n"

            user_queries = [msg["content"] for msg in self.local_conversation_history if msg["role"] == "user"]
            tools_count = self.agent_state['tools_executed']

            if user_queries:
                summary += "Main queries:\n"
                for i, query in enumerate(user_queries[:3], 1):
                    preview = query[:100] + ('...' if len(query) > 100 else '')
                    summary += f"{i}. {preview}\n"
                summary += "\n"

            summary += f"Tools executed: {tools_count}\n\n"

            timestamp = int(time.time())
            with open(summary_path / f"{timestamp}_summary.txt", "w") as f:
                f.write(summary)

            with open(summary_path / "last_session.txt", "w") as f:
                f.write(summary)

            logger.info(f"Session summary saved")

        except Exception as e:
            logger.error(f"Error saving session summary: {e}")
