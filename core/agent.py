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

from core.llm_client import get_llm_client
from core.memory_manager import MemoryManager
from core.system_control import SystemControl
from core.task_manager import TaskManager
from core.session_manager import SessionManager
import networkx as nx

logger = logging.getLogger(__name__)

class CommandResult:
    def __init__(self, stdout: str, stderr: str, code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.code = code
        self.success = (code == 0)
        self.timestamp = datetime.now()

    @property
    def output(self) -> str:
        return self.stdout if self.stdout else self.stderr

    def to_dict(self) -> Dict[str, Any]:
        return {
            'stdout': self.stdout,
            'stderr': self.stderr,
            'code': self.code,
            'success': self.success,
            'timestamp': self.timestamp.isoformat()
        }

class CommandExtractor:
    COMMAND_TAGS = ['bash', 'python']
    THINKING_TAG = 'thinking'
    DECISION_TAG = 'decision'
    PLAN_TAG = 'plan'
    SUMMARY_TAG = 'summary'
    TASK_TAG = 'task'
    SUBTASK_TAG = 'subtask'
    FILE_OP_TAGS = ['view', 'edit', 'replace', 'glob', 'grep', 'ls']
    USER_INPUT_TAG = 'user_input'

    @staticmethod
    def extract_commands(response: str) -> List[Tuple[str, str]]:
        commands = []
        CommandExtractor._extract_tag_commands(response, CommandExtractor.COMMAND_TAGS, commands)
        CommandExtractor._extract_tag_commands(response, CommandExtractor.FILE_OP_TAGS, commands)
        return commands

    @staticmethod
    def _extract_tag_commands(response: str, tags: List[str], commands: List[Tuple[str, str]]) -> None:
        for tag in tags:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = list(re.finditer(pattern, response, re.DOTALL))
            if matches:
                for match in matches:
                    command = match.group(1)
                    if command:
                        # Removed full strip to preserve indentation. Only strip trailing newlines.
                        command = command.rstrip('\r\n')
                        commands.append((tag, command))
            else:
                open_tag_pattern = f"<{tag}>"
                close_tag_pattern = f"</{tag}>"
                starts = [m.end() for m in re.finditer(open_tag_pattern, response)]
                ends = [m.start() for m in re.finditer(close_tag_pattern, response)]
                for start in starts:
                    valid_ends = [e for e in ends if e > start]
                    if valid_ends:
                        end = min(valid_ends)
                        command = response[start:end]
                        if command:
                            command = command.rstrip('\r\n')
                            commands.append((tag, command))

    @staticmethod
    def extract_thinking(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.THINKING_TAG)

    @staticmethod
    def extract_decision(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.DECISION_TAG)

    @staticmethod
    def extract_plan(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.PLAN_TAG)

    @staticmethod
    def extract_summary(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.SUMMARY_TAG)

    @staticmethod
    def extract_tasks(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.TASK_TAG)

    @staticmethod
    def extract_subtasks(response: str) -> List[str]:
        return CommandExtractor._extract_tag_content(response, CommandExtractor.SUBTASK_TAG)

    @staticmethod
    def extract_user_input_requests(response: str) -> List[str]:
        standard_requests = CommandExtractor._extract_tag_content(response, CommandExtractor.USER_INPUT_TAG)
        alt_pattern = r"\[PAUSE_FOR_USER_INPUT\](.*?)\[/PAUSE_FOR_USER_INPUT\]"
        alt_matches = re.finditer(alt_pattern, response, re.DOTALL)
        alt_requests = [match.group(1).strip() for match in alt_matches]
        return standard_requests + alt_requests

    @staticmethod
    def _extract_tag_content(response: str, tag: str) -> List[str]:
        pattern = f"<{tag}>(.*?)</{tag}>"
        matches = list(re.finditer(pattern, response, re.DOTALL))
        results = [m.group(1).strip() for m in matches]
        if not results:
            open_tag_pattern = f"<{tag}>"
            close_tag_pattern = f"</{tag}>"
            starts = [m.end() for m in re.finditer(open_tag_pattern, response)]
            ends = [m.start() for m in re.finditer(close_tag_pattern, response)]
            for start in starts:
                valid_ends = [e for e in ends if e > start]
                if valid_ends:
                    end = min(valid_ends)
                    content = response[start:end].strip()
                    if content:
                        results.append(content)
        return results

    @staticmethod
    def extract_heredocs(response: str) -> List[Dict[str, str]]:
        heredocs = []
        heredoc_pattern = r'cat\s*<<\s*EOF\s*>\s*([^\n]+)(.*?)EOF'
        matches = re.finditer(heredoc_pattern, response, re.DOTALL)
        for match in matches:
            filename = match.group(1).strip()
            content = match.group(2)
            heredocs.append({'filename': filename, 'content': content})
        if not heredocs:
            current_doc = None
            content_lines = []
            for line in response.split('\n'):
                if not current_doc and ('cat << EOF >' in line or 'cat <<EOF >' in line):
                    parts = line.strip().split('>')
                    if len(parts) > 1:
                        current_doc = parts[1].strip()
                        continue
                elif line.strip() == 'EOF' and current_doc:
                    heredocs.append({
                        'filename': current_doc,
                        'content': '\n'.join(content_lines)
                    })
                    current_doc = None
                    content_lines = []
                    continue
                if current_doc:
                    content_lines.append(line)
        return heredocs

    @staticmethod
    def is_exit_command(command_type: str, command: str) -> bool:
        lower_cmd = command.strip().lower()
        exit_cmds = {"exit", "quit", "bye", "done"}
        if lower_cmd in exit_cmds:
            return True
        for exit_cmd in exit_cmds:
            if lower_cmd.startswith(f"{exit_cmd} "):
                return True
        return False

class AutonomousAgent:
    def __init__(
        self,
        memory_manager: MemoryManager = None,
        session_manager: SessionManager = None,
        api_key: str = "",
        model: str = "deepseek",
        test_mode: bool = False
    ):
        if not api_key:
            raise ValueError("API key required")
        self.last_assistant_response = None
        self.paused_for_human_context = False
        self.memory_manager = memory_manager or MemoryManager()
        self.memory_path = self.memory_manager.base_path
        self._setup_storage()
        self.system_control = SystemControl(test_mode=test_mode)
        self.task_manager = TaskManager(self.memory_path)
        self.session_manager = session_manager or SessionManager(self.memory_path, self.memory_manager)
        self.agent_id = str(uuid.uuid4())[:8]
        self.agent_state = {
            'started_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'commands_executed': 0,
            'tasks_completed': 0,
            'memory_operations': 0,
            'status': 'initializing',
            'last_error': None,
            'current_task': None,
        }
        if not (self.memory_path / "vector_index").exists():
            try:
                system_prompt_path = Path("config/system_prompt.md")
                if system_prompt_path.exists():
                    self.memory_manager.save_document(
                        "system_guide",
                        system_prompt_path.read_text(),
                        tags=["system", "guide", "permanent"],
                        permanent=True
                    )
                    self.memory_manager.save_document(
                        "agent_identity",
                        f"Agent ID: {self.agent_id}\nInitialized: {self.agent_state['started_at']}\nModel: {model}",
                        tags=["system", "identity", "permanent"],
                        permanent=True
                    )
            except Exception as e:
                logger.error(f"Error seeding memory: {e}")
        self.reflections = []
        self.planned_steps = []
        self.executive_summary = ""
        self.llm = get_llm_client(model, api_key)
        self.model_name = model
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.command_extractor = CommandExtractor()
        self.should_exit = False
        self.command_history = []
        self.heartbeat_task = None
        self.resource_monitor_task = None
        self.test_mode = test_mode
        self.local_conversation_history: List[Dict[str, str]] = []
        self.working_memory: Dict[str, Any] = {}
        self.agent_state['status'] = 'ready'

    async def run(self, initial_prompt: str, system_prompt: str) -> None:
        try:
            self.agent_state['status'] = 'running'
            self.agent_state['current_task'] = initial_prompt[:100] + ("..." if len(initial_prompt) > 100 else "")
            self.agent_state['last_active'] = datetime.now().isoformat()
            print("\nInitializing new session...")
            self.heartbeat_task = asyncio.create_task(self.heartbeat())
            self.resource_monitor_task = asyncio.create_task(self._monitor_resources())
            session_id = f"{int(time.time())}_{self.agent_id}"
            self.memory_manager.save_document(
                f"session_start_{session_id}",
                f"Session started at {datetime.now().isoformat()}\nInitial task: {initial_prompt}",
                tags=["session", "meta", "start"],
                metadata={
                    "session_id": session_id,
                    "model": self.model_name,
                    "agent_id": self.agent_id
                }
            )
            env = dict(os.environ)
            working_dir = str(Path.cwd())
            self.session_manager.start_session(
                shell_preference="bash",
                working_directory=working_dir,
                environment=env,
                session_id=session_id
            )
            self.working_memory['working_directory'] = working_dir
            self.working_memory['session_id'] = session_id
            enhanced_system_prompt = self._enhance_system_prompt(system_prompt)
            system_msg = {"role": "system", "content": enhanced_system_prompt}
            self.local_conversation_history.append(system_msg)
            user_msg = {"role": "user", "content": initial_prompt}
            self.local_conversation_history.append(user_msg)
            consecutive_failures = 0
            max_failures = 3
            self.memory_manager.save_document(
                f"task_{session_id}",
                initial_prompt,
                tags=["task", "user_request"],
                metadata={"session_id": session_id, "status": "started"}
            )
            turn_count = 0
            while not self.should_exit:
                turn_count += 1
                turn_start_time = time.time()
                try:
                    self.agent_state['last_active'] = datetime.now().isoformat()
                    self.agent_state['turn_count'] = turn_count
                    compressed_history = await self.compress_context(self.local_conversation_history)
                    await self._save_working_memory_state()
                    llm_timeout = 120
                    max_retries = 3
                    retry_count = 0
                    retry_delay = 2
                    response = ""
                    while retry_count < max_retries:
                        try:
                            response = await asyncio.wait_for(
                                self.llm.get_response(
                                    prompt=None,
                                    system=None,
                                    conversation_history=compressed_history,
                                    tool_usage=False
                                ),
                                timeout=llm_timeout
                            )
                            if response:
                                break
                            retry_count += 1
                            if retry_count >= max_retries:
                                logger.error(f"LLM call failed after {max_retries} attempts")
                                response = "I had issues connecting to the API. Let me attempt a simpler approach."
                                break
                            logger.warning(f"Retrying LLM call (attempt {retry_count}/{max_retries})")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        except (asyncio.TimeoutError, Exception) as api_error:
                            retry_count += 1
                            logger.error(f"LLM API error (attempt {retry_count}/{max_retries}): {str(api_error)}")
                            if retry_count >= max_retries:
                                if isinstance(api_error, asyncio.TimeoutError):
                                    response = "My response took too long to generate. Trying a simpler approach."
                                else:
                                    response = f"I encountered an error: {str(api_error)}. Trying a different approach."
                                break
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                    if not response:
                        logger.warning("No response from LLM.")
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            error_msg = f"Too many consecutive failures ({max_failures}). Ending session."
                            print(error_msg)
                            self.memory_manager.save_document(
                                f"error_{session_id}_{int(time.time())}",
                                error_msg,
                                tags=["error", "consecutive_failures"],
                                metadata={"session_id": session_id, "turn": turn_count}
                            )
                            break
                        continue
                    consecutive_failures = 0
                    assistant_msg = {"role": "assistant", "content": response}
                    self.local_conversation_history.append(assistant_msg)
                    self._print_response(response)
                    self.last_assistant_response = response
                    should_pause, question = await self.llm.check_for_user_input_request(response)
                    if should_pause:
                        user_input = await self._request_user_input(question)
                        user_input_msg = {"role": "user", "content": f"You asked: {question}\n\nMy response: {user_input}"}
                        self.local_conversation_history.append(user_input_msg)
                        continue
                    await self._process_reasoning_blocks(response, session_id, turn_count)
                    await self.process_heredocs(response)
                    commands = self.command_extractor.extract_commands(response)
                    if not commands:
                        await self._handle_no_commands(response, session_id, turn_count)
                        continue
                    all_outputs = await self._execute_commands(commands, session_id, turn_count)
                    if self.should_exit:
                        break
                    if all_outputs:
                        combined_message = "\n\n".join(all_outputs)
                        slash_cmd = None
                        for output in all_outputs:
                            lines = output.strip().split('\n')
                            for line in lines:
                                if line.strip().startswith('/') and len(line.strip().split()) == 1:
                                    slash_cmd = line.strip().lower()
                                    break
                            if slash_cmd:
                                break
                        if slash_cmd == '/compact':
                            print("\nDetected /compact command in output. Compacting context...")
                            compressed_history = await self.compress_context(self.local_conversation_history, force=True)
                            self.local_conversation_history = compressed_history
                            filtered_message = combined_message.replace('/compact', '(Context compacted)')
                            next_user_msg = {"role": "user", "content": filtered_message}
                        elif slash_cmd == '/pause':
                            print("\n==================================================")
                            print("CONVERSATION PAUSED FOR ADDITIONAL CONTEXT")
                            print("Enter additional context and press Enter on a blank line to finish.")
                            print("--------------------------------------------------")
                            lines = []
                            while True:
                                try:
                                    line = input()
                                    if not line.strip():
                                        break
                                    lines.append(line)
                                except EOFError:
                                    break
                            additional_context = "\n".join(lines)
                            if additional_context.strip():
                                await self.add_human_context(additional_context)
                                print("Context added. Continuing...\n")
                                filtered_message = combined_message.replace('/pause', '(Context added)')
                                next_user_msg = {
                                    "role": "user",
                                    "content": f"{filtered_message}\n\nAdditional context added above."
                                }
                            else:
                                filtered_message = combined_message.replace('/pause', '(Pause requested, no context added)')
                                next_user_msg = {"role": "user", "content": filtered_message}
                        elif slash_cmd == '/help':
                            help_text = "\nAvailable Commands:\n  /help\n  /compact\n  /pause\n"
                            print(help_text)
                            filtered_message = combined_message.replace('/help', '(Help displayed)')
                            next_user_msg = {"role": "user", "content": filtered_message}
                        else:
                            next_user_msg = {"role": "user", "content": combined_message}
                        self.local_conversation_history.append(next_user_msg)
                        if turn_count % 5 == 0:
                            self.memory_manager.create_backup()
                    turn_duration = time.time() - turn_start_time
                    logger.info(f"Turn {turn_count} completed in {turn_duration:.2f}s")
                    if 'performance' not in self.working_memory:
                        self.working_memory['performance'] = []
                    self.working_memory['performance'].append({
                        'turn': turn_count,
                        'duration': turn_duration,
                        'timestamp': time.time(),
                        'commands_executed': len(commands) if commands else 0
                    })
                except Exception as turn_error:
                    logger.error(f"Error during conversation turn: {turn_error}")
                    consecutive_failures += 1
                    error_msg = f"Error during turn {turn_count}: {str(turn_error)}"
                    self.agent_state['last_error'] = error_msg
                    self.memory_manager.save_document(
                        f"error_{session_id}_{int(time.time())}",
                        error_msg,
                        tags=["error", "turn_failure"],
                        metadata={"session_id": session_id, "turn": turn_count, "error": str(turn_error)}
                    )
                    user_msg = {
                        "role": "user", 
                        "content": f"An error occurred: {str(turn_error)}. Please continue differently."
                    }
                    self.local_conversation_history.append(user_msg)
                    if consecutive_failures >= max_failures:
                        print(f"Too many consecutive failures ({max_failures}). Ending.")
                        break
            if self.should_exit:
                print("\nSession ended by agent.")
            else:
                print("\nSession completed or stopped due to errors.")
            self.memory_manager.save_document(
                f"session_end_{session_id}",
                f"Session ended at {datetime.now().isoformat()}\nTurns: {turn_count}\nExit requested: {self.should_exit}",
                tags=["session", "meta", "end"],
                metadata={
                    "session_id": session_id,
                    "turns": turn_count,
                    "requested_exit": self.should_exit,
                    "duration": (datetime.now() - datetime.fromisoformat(self.agent_state['started_at'])).total_seconds()
                }
            )
            await self._generate_final_reflection(session_id, turn_count)
        except Exception as e:
            logger.error(f"Run failed: {e}")
            self.memory_manager.create_backup(force=True)
            self.agent_state['status'] = 'error'
            self.agent_state['last_error'] = str(e)
            raise
        finally:
            print("\nCleaning up...")
            self.agent_state['status'] = 'inactive'
            self.agent_state['last_active'] = datetime.now().isoformat()
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    logger.debug("heartbeat task canceled")
            if self.resource_monitor_task and not self.resource_monitor_task.done():
                self.resource_monitor_task.cancel()
                try:
                    await self.resource_monitor_task
                except asyncio.CancelledError:
                    logger.debug("resource_monitor task canceled")
            self.cleanup()

    async def process_heredocs(self, response: str) -> List[str]:
        heredocs = self.command_extractor.extract_heredocs(response)
        created_files = []
        for doc in heredocs:
            try:
                filepath = Path(doc['filename'])
                filepath.parent.mkdir(parents=True, exist_ok=True)
                with open(filepath, 'w') as f:
                    f.write(doc['content'])
                logger.info(f"Created file: {filepath}")
                created_files.append(str(filepath))
                if 'created_files' not in self.working_memory:
                    self.working_memory['created_files'] = []
                self.working_memory['created_files'].append({
                    'path': str(filepath),
                    'timestamp': time.time(),
                    'size': len(doc['content'])
                })
                if any(str(filepath).endswith(ext) for ext in ['.py', '.json', '.md', '.sh', '.yaml', '.yml', '.conf', '.txt']):
                    if 'important_files' not in self.working_memory:
                        self.working_memory['important_files'] = []
                    if str(filepath) not in self.working_memory['important_files']:
                        self.working_memory['important_files'].append(str(filepath))
            except Exception as e:
                logger.error(f"Error creating file {doc['filename']}: {e}")
        return created_files

    def _setup_storage(self):
        dirs = [
            'conversations',
            'logs',
            'summaries',
            'config',
            'scripts',
            'data',
            'temp',
            'state',
            'sessions',
            'reflections',
            'working_memory',
            'tasks',
            'plans',
            'archive',
            'notes'
        ]
        for dir_name in dirs:
            (self.memory_path / dir_name).mkdir(parents=True, exist_ok=True)

    async def _save_working_memory_state(self):
        try:
            if not self.working_memory:
                return
            timestamp = int(time.time())
            memory_file = self.memory_path / "working_memory" / f"state_{timestamp}.json"
            with open(memory_file, 'w') as f:
                json.dump(self.working_memory, f, indent=2, default=str)
            memory_files = sorted(list((self.memory_path / "working_memory").glob("state_*.json")), 
                                  key=lambda f: f.stat().st_mtime)
            if len(memory_files) > 10:
                for old_file in memory_files[:-10]:
                    old_file.unlink()
        except Exception as e:
            logger.error(f"Error saving working memory state: {e}")

    def _enhance_system_prompt(self, system_prompt: str) -> str:
        try:
            system_info = self._detect_system_info()
            identity_section = f"\n# Agent Identity\n- Agent ID: {self.agent_id}\n- Started: {self.agent_state['started_at']}\n"
            system_info_section = f"\n# System Info\n- OS: {system_info.get('os_type', 'Unknown')}\n"
            combined_prompt = f"{system_prompt}\n\n{identity_section}{system_info_section}"
            return combined_prompt
        except Exception as e:
            logger.error(f"Error enhancing system prompt: {e}")
            return system_prompt

    def _detect_system_info(self) -> dict:
        info = {'os_type': 'Unknown'}
        try:
            if os.name == 'posix':
                info['os_type'] = 'Linux/Unix'
            elif os.name == 'nt':
                info['os_type'] = 'Windows'
            elif os.name == 'darwin':
                info['os_type'] = 'macOS'
            self.working_memory['system_info'] = info
        except Exception as e:
            logger.error(f"Error detecting system info: {e}")
        return info

    def _load_last_session(self) -> Optional[str]:
        summary_path = self.memory_path / "summaries/last_session.txt"
        try:
            if summary_path.exists():
                with open(summary_path) as f:
                    return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading last session: {e}")
        return None

    def _save_session_summary(self, summary: str):
        try:
            with open(self.memory_path / "summaries/last_session.txt", 'w') as f:
                f.write(summary)
        except Exception as e:
            logger.error(f"Error saving session summary: {e}")

    def _print_response(self, content: str):
        message_match = re.search(r'<message>(.*?)</message>', content, re.DOTALL)
        message_content = message_match.group(1).strip() if message_match else None
        commands = []
        for tag in self.command_extractor.COMMAND_TAGS:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, content, re.DOTALL)
            for match in matches:
                cmd = match.group(1).strip()
                if tag == "bash" and len(cmd.split('\n')) > 1:
                    cmd_first_line = cmd.split('\n')[0]
                    commands.append(f"$ {cmd_first_line}")
                else:
                    if len(cmd) > 100:
                        cmd = cmd[:97] + "..."
                    commands.append(f"$ {cmd}")
        file_ops = []
        for tag in self.command_extractor.FILE_OP_TAGS:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, content, re.DOTALL)
            for match in matches:
                cmd = match.group(1).strip()
                params = {}
                try:
                    if cmd.strip().startswith('{') and cmd.strip().endswith('}'):
                        params = json.loads(cmd)
                    else:
                        for line in cmd.split('\n'):
                            if ':' in line:
                                key, value = line.split(':', 1)
                                params[key.strip()] = value.strip()
                except:
                    pass
                if tag == "view" and "file_path" in params:
                    file_ops.append(f"📄 Reading {params['file_path']}")
                elif tag == "edit" and "file_path" in params:
                    file_ops.append(f"✏️ Editing {params['file_path']}")
                elif tag == "replace" and "file_path" in params:
                    file_ops.append(f"🔄 Replacing {params['file_path']}")
                elif tag == "glob" and "pattern" in params:
                    file_ops.append(f"🔍 Finding files matching {params['pattern']}")
                elif tag == "grep" and "pattern" in params:
                    file_ops.append(f"🔍 Searching '{params['pattern']}' in files")
                elif tag == "ls" and "path" in params:
                    file_ops.append(f"📁 Listing {params['path']}")
                else:
                    file_ops.append(f"{tag.upper()}: File op")
        thinking_blocks = self.command_extractor.extract_thinking(content)
        planning_blocks = self.command_extractor.extract_plan(content)
        print("\n", end="")
        if message_content:
            print(message_content.strip())
            print("")
        if commands:
            print("Commands:")
            for cmd in commands:
                print(f"  {cmd}")
            print("")
        if file_ops:
            print("File Operations:")
            for op in file_ops:
                print(f"  {op}")
            print("")
        if not message_content and not commands and not file_ops:
            clean_content = re.sub(r'<[^>]+>', '', content)
            print(clean_content.strip())
        if hasattr(self.memory_manager, 'update_conversation_metrics'):
            self.memory_manager.update_conversation_metrics()

    def archive_session(self):
        timestamp = int(datetime.now().timestamp())
        session_filename = f"{timestamp}_session.json"
        session_path = self.memory_path / "sessions" / session_filename
        summary = self._generate_session_summary()
        data_to_save = {
            "conversation": self.local_conversation_history,
            "ended_at": datetime.now().isoformat(),
            "summary": summary
        }
        try:
            (self.memory_path / "sessions").mkdir(exist_ok=True)
            with open(session_path, "w") as f:
                json.dump(data_to_save, f, indent=2)
            summary_file = self.memory_path / "summaries" / f"{timestamp}_summary.txt"
            (self.memory_path / "summaries").mkdir(exist_ok=True)
            with open(summary_file, "w") as f:
                f.write(summary)
            with open(self.memory_path / "summaries/last_session.txt", "w") as f:
                f.write(summary)
        except Exception as e:
            logger.error(f"Error writing session archive: {e}")
        try:
            conversation_id = f"session_{timestamp}"
            self.memory_manager.save_conversation(
                conversation_id,
                messages=self.local_conversation_history,
                metadata={"archived_at": datetime.now().isoformat(), "summary": summary}
            )
        except Exception as e:
            logger.error(f"Error saving session to memory graph: {e}")

    def _generate_session_summary(self) -> str:
        try:
            user_msgs = [m['content'] for m in self.local_conversation_history if m.get('role') == 'user']
            assistant_msgs = [m['content'] for m in self.local_conversation_history if m.get('role') == 'assistant']
            decisions = []
            plans = []
            summaries = []
            thinking = []
            for msg in assistant_msgs:
                decisions.extend(self.command_extractor.extract_decision(msg))
                plans.extend(self.command_extractor.extract_plan(msg))
                summaries.extend(self.command_extractor.extract_summary(msg))
                thinking.extend(self.command_extractor.extract_thinking(msg))
            commands_by_type = {}
            for msg in assistant_msgs:
                for tag in self.command_extractor.COMMAND_TAGS:
                    pattern = f"<{tag}>(.*?)</{tag}>"
                    matches = re.finditer(pattern, msg, re.DOTALL)
                    for match in matches:
                        cmd = match.group(1).split('\n')[0]
                        if tag not in commands_by_type:
                            commands_by_type[tag] = []
                        commands_by_type[tag].append(cmd)
            summary_parts = []
            summary_parts.append("# Session Summary")
            summary_parts.append(f"Generated: {datetime.now().isoformat()}")
            summary_parts.append(f"Session ID: {self.agent_id}")
            summary_parts.append(f"Exchanges: {len(self.local_conversation_history)//2}")
            if user_msgs:
                summary_parts.append("\n## Initial Task")
                init_task = user_msgs[0]
                if len(init_task) > 500:
                    summary_parts.append(init_task[:500] + "...")
                else:
                    summary_parts.append(init_task)
            if decisions:
                summary_parts.append("\n## Key Decisions")
                for i, decision in enumerate(decisions[:3]):
                    txt = decision.replace('\n', ' ')[:300]
                    summary_parts.append(f"{i+1}. {txt}")
            if plans:
                summary_parts.append("\n## Plans")
                for plan in plans[:2]:
                    summary_parts.append(plan[:300])
            if commands_by_type:
                summary_parts.append("\n## Commands Executed")
                for tag, cmds in commands_by_type.items():
                    summary_parts.append(f"{tag.upper()} commands:")
                    for c in cmds[:5]:
                        summary_parts.append(f"- {c[:120]}")
            if summaries:
                summary_parts.append("\n## Final Summary")
                summary_parts.append(summaries[-1][:500])
            return "\n".join(summary_parts)
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Session ended at {datetime.now().isoformat()}"

    def cleanup(self):
        try:
            self.memory_manager.create_backup()
            history_path = self.memory_path / "state/command_history.json"
            (self.memory_path / "state").mkdir(exist_ok=True)
            with open(history_path, 'w') as f:
                json.dump(self.command_history, f, indent=2)
            self.system_control.cleanup()
            self.archive_session()
            logger.info("Agent cleanup done")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def add_human_context(self, additional_context: str):
        self.paused_for_human_context = True
        try:
            if self.local_conversation_history and self.local_conversation_history[-1].get('role') == 'assistant':
                last_assistant_msg = self.local_conversation_history.pop()
                original_content = last_assistant_msg['content']
                formatted = f"{original_content}\n\n[HUMAN_ADDED_CONTEXT]\n{additional_context}\n[/HUMAN_ADDED_CONTEXT]\n"
                merged_msg = {"role": "assistant", "content": formatted}
                self.local_conversation_history.append(merged_msg)
                self.last_assistant_response = formatted
                if 'human_context_additions' not in self.working_memory:
                    self.working_memory['human_context_additions'] = []
                self.working_memory['human_context_additions'].append({
                    'timestamp': datetime.now().isoformat(),
                    'context_added': additional_context,
                    'turn': len(self.local_conversation_history) // 2
                })
                try:
                    self.memory_manager.save_document(
                        f"human_context_{int(time.time())}",
                        f"Additional context at turn {len(self.local_conversation_history)//2}:\n\n{additional_context}",
                        tags=["human_context", "conversation", "pause"],
                        metadata={"timestamp": time.time()}
                    )
                except Exception as e:
                    logger.error(f"Error saving human context: {e}")
            else:
                logger.warning("No previous assistant response to add context to")
        except Exception as e:
            logger.error(f"Error adding human context: {e}")
        finally:
            self.paused_for_human_context = False

    async def heartbeat(self):
        try:
            heartbeat_interval = 120
            while not self.should_exit:
                self.agent_state['heartbeat'] = datetime.now().isoformat()
                self._save_state()
                self.memory_manager.create_backup()
                await self._health_check()
                await asyncio.sleep(heartbeat_interval)
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    async def _health_check(self):
        try:
            working_memory_size = len(json.dumps(self.working_memory))
            if working_memory_size > 500000:
                logger.warning(f"Working memory too large: {working_memory_size} bytes. Pruning...")
                await self._prune_working_memory()
            stats = {
                'uptime': (datetime.now() - datetime.fromisoformat(self.agent_state['started_at'])).total_seconds(),
                'working_memory_size': working_memory_size,
                'conversation_turns': len(self.local_conversation_history) // 2,
                'commands_executed': self.agent_state.get('commands_executed', 0)
            }
            logger.info(f"Agent health check: {stats}")
            if time.time() % 3600 < 120:
                self.memory_manager.save_document(
                    f"health_check_{int(time.time())}",
                    f"Health check at {datetime.now().isoformat()}\n" +
                    "\n".join([f"{k}: {v}" for k, v in stats.items()]),
                    tags=["health", "monitoring"],
                    metadata=stats
                )
        except Exception as e:
            logger.error(f"Health check error: {e}")

    async def _monitor_resources(self):
        try:
            while not self.should_exit:
                await self.system_control.monitor_resources()
                await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Resource monitoring error: {e}")

    async def _prune_working_memory(self):
        try:
            essential_keys = {'working_directory', 'session_id', 'current_task', 'important_files'}
            preserve = {k: self.working_memory[k] for k in essential_keys if k in self.working_memory}
            if 'performance' in self.working_memory and isinstance(self.working_memory['performance'], list):
                preserve['performance'] = self.working_memory['performance'][-10:]
            old_size = len(json.dumps(self.working_memory))
            self.working_memory = preserve
            new_size = len(json.dumps(self.working_memory))
            logger.info(f"Pruned working memory from {old_size} to {new_size} bytes")
            self.memory_manager.save_document(
                f"working_memory_snapshot_{int(time.time())}",
                json.dumps(self.working_memory, indent=2),
                tags=["memory", "snapshot", "pruned"],
                metadata={"reason": "size_limit_exceeded", "old_size": old_size, "new_size": new_size}
            )
        except Exception as e:
            logger.error(f"Error pruning working memory: {e}")

    def _save_state(self):
        try:
            tasks = self.task_manager.active_tasks
            state = {
                "tasks": tasks,
                "environment": dict(os.environ),
                "last_commands": self.command_history[-10:] if self.command_history else [],
                "session_summary": self.last_session_summary,
                "conversation_length": len(self.local_conversation_history),
                "last_heartbeat": datetime.now().isoformat(),
                "system_stats": {
                    "memory_nodes": len(self.memory_manager.graph.graph.nodes),
                    "command_history_length": len(self.memory_manager.command_history)
                }
            }
            self.memory_manager.save_document(
                "system_state",
                json.dumps(state, indent=2),
                tags=["system", "state", "heartbeat"],
                metadata={"timestamp": time.time()}
            )
            logger.info(f"State saved - {len(state['tasks'])} tasks, {state['conversation_length']} messages")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
            try:
                self.memory_manager.save_document(
                    "emergency_state", 
                    json.dumps({"error": str(e), "timestamp": time.time()}),
                    tags=["system", "error"]
                )
            except:
                pass

    async def compress_context(self, messages: List[Dict], token_limit: int = 16000, force: bool = False) -> List[Dict]:
        estimated_tokens = sum(len(str(msg.get('content', ''))) for msg in messages) // 4
        if estimated_tokens <= token_limit and not force:
            return messages
        try:
            compression_start = time.time()
            pre_compression_size = estimated_tokens
            system_messages = [msg for msg in messages if msg.get('role') == 'system']
            user_messages = [msg for msg in messages if msg.get('role') == 'user']
            assistant_messages = [msg for msg in messages if msg.get('role') == 'assistant']
            kept_messages = system_messages.copy()
            scored_messages = []
            if user_messages:
                initial_msg = user_messages[0]
                scored_messages.append((initial_msg, 10, 0))
            for i, msg in enumerate(assistant_messages):
                score = 0
                content = msg.get('content', '')
                if re.search(r'```[a-z]*\n[\s\S]*?\n```', content):
                    score += 5
                if len(CommandExtractor.extract_decision(content)) > 0:
                    score += 8
                if len(CommandExtractor.extract_plan(content)) > 0:
                    score += 7
                if len(CommandExtractor.extract_tasks(content)) > 0:
                    score += 6
                if re.findall(r'<(bash|python)>.*?</(bash|python)>', content, re.DOTALL):
                    score += 4
                if len(CommandExtractor.extract_summary(content)) > 0:
                    score += 5
                recency_boost = max(0, 5 - min(5, (len(assistant_messages) - i)))
                score += recency_boost
                original_index = messages.index(msg)
                scored_messages.append((msg, score, original_index))
            for i, msg in enumerate(user_messages[1:], 1):
                score = 0
                content = msg.get('content', '')
                if re.search(r'```[a-z]*\n[\s\S]*?\n```', content):
                    score += 5
                if '?' in content:
                    score += 4
                if any(cmd in content.lower() for cmd in ['create', 'build', 'fix']):
                    score += 3
                recency_boost = max(0, 5 - min(5, (len(user_messages) - i)))
                score += recency_boost
                original_index = messages.index(msg)
                scored_messages.append((msg, score, original_index))
            scored_messages.sort(key=lambda x: x[1], reverse=True)
            base_exchanges = 3
            if estimated_tokens > token_limit * 1.5:
                exchanges_to_keep = 2
            elif estimated_tokens <= token_limit * 1.2:
                exchanges_to_keep = min(5, len(user_messages))
            else:
                exchanges_to_keep = base_exchanges
            for i in range(1, exchanges_to_keep + 1):
                if i <= len(user_messages):
                    user_msg = user_messages[-i]
                    if user_msg not in [m for m, _, _ in scored_messages[:exchanges_to_keep]]:
                        scored_messages.insert(exchanges_to_keep, (user_msg, 100 - i, messages.index(user_msg)))
                    if i <= len(assistant_messages):
                        asst_msg = assistant_messages[-i]
                        scored_messages.insert(exchanges_to_keep*2, (asst_msg, 100 - i, messages.index(asst_msg)))
            token_target = token_limit * 0.7
            kept_tokens = sum(len(str(msg.get('content', ''))) for msg in system_messages) // 4
            high_value_messages = []
            for msg, score, original_index in scored_messages:
                msg_tokens = len(str(msg.get('content', ''))) // 4
                if kept_tokens + msg_tokens <= token_target:
                    high_value_messages.append((msg, original_index))
                    kept_tokens += msg_tokens
                else:
                    break
            high_value_messages.sort(key=lambda x: x[1])
            for msg, _ in high_value_messages:
                if msg not in kept_messages:
                    kept_messages.append(msg)
            to_summarize = [m for m in messages if m not in kept_messages]
            if not to_summarize:
                return kept_messages
            summary_parts = ["## PREVIOUS CONVERSATION SUMMARY"]
            summary_parts.append(f"(Compressed {len(to_summarize)} older messages)")
            summary = "\n".join(summary_parts)
            summary_doc_id = f"context_summary_{int(time.time())}"
            metadata = {
                "original_messages": len(messages),
                "kept_messages": len(kept_messages),
                "summarized_messages": len(to_summarize),
                "original_tokens": pre_compression_size,
                "turn_count": getattr(self.memory_manager, "conversation_turn_count", 0),
                "high_value_messages": len(high_value_messages)
            }
            if 'session_id' in self.working_memory:
                metadata["session_id"] = self.working_memory['session_id']
            self.memory_manager.save_document(
                summary_doc_id,
                summary,
                tags=["summary", "context", "compression", "session_state"],
                metadata=metadata
            )
            kept_messages.insert(0 if not system_messages else 1, {"role": "system", "content": summary})
            post_size = sum(len(str(msg.get('content', ''))) for msg in kept_messages) // 4
            compression_time = time.time() - compression_start
            logger.info(f"Compressed from {pre_compression_size} to {post_size} tokens in {compression_time:.2f}s")
            if force:
                print(f"✅ Context compressed: {pre_compression_size} → {post_size} tokens.")
            return kept_messages
        except Exception as e:
            logger.error(f"Error during context compression: {e}")
            try:
                system_msgs = [msg for msg in messages if msg.get('role') == 'system']
                non_system_msgs = [msg for msg in messages if msg.get('role') != 'system']
                fallback_msgs = system_msgs + non_system_msgs[-10:] if len(non_system_msgs) > 10 else non_system_msgs
                logger.warning("Using fallback compression.")
                return fallback_msgs
            except:
                logger.error("Critical compression failure.")
                return messages[-10:] if len(messages) > 10 else messages

    async def _handle_no_commands(self, response: str, session_id: str, turn_count: int) -> None:
        try:
            completion_signals = ["session_end", "task complete", "all done", "completed successfully", "done"]
            if any(signal in response.lower() for signal in completion_signals):
                self.memory_manager.save_document(
                    f"task_completion_{session_id}_{turn_count}",
                    f"Task completed at turn {turn_count}.\nFinal message: {response[:500]}",
                    tags=["task", "completion"],
                    metadata={"session_id": session_id, "turn": turn_count, "status": "completed"}
                )
                print("Agent declared completion. Ending session.")
                self.should_exit = True
                self.agent_state['status'] = 'completed'
                self.agent_state['tasks_completed'] += 1
                return
            next_user_msg = {"role": "user", "content": "(No commands found - Provide commands or exit.)"}
            self.local_conversation_history.append(next_user_msg)
            logger.info(f"No commands found in turn {turn_count}")
        except Exception as e:
            logger.error(f"Error handling no commands: {e}")

    async def _execute_commands(self, commands: List[Tuple[str, str]], session_id: str, turn_count: int) -> List[str]:
        all_outputs = []
        command_execution_errors = 0
        max_command_errors = 3
        self.agent_state['last_active'] = datetime.now().isoformat()
        for cmd_idx, (cmd_type, cmd_content) in enumerate(commands):
            if self.command_extractor.is_exit_command(cmd_type, cmd_content):
                print("Exit command found. Stopping session.")
                self.should_exit = True
                break
            cmd_id = f"{session_id}_{turn_count}_{cmd_idx}"
            logger.info(f"Executing command {cmd_id}: {cmd_type} - {cmd_content[:50]}...")
            standard_timeout = 120
            if any(slow_cmd in cmd_content.lower() for slow_cmd in 
                   ['install', 'update', 'upgrade', 'train', 'download', 'build', 'compile']):
                command_timeout = 300
            else:
                command_timeout = standard_timeout
            self.memory_manager.save_document(
                f"command_{cmd_id}",
                f"Type: {cmd_type}\nCommand:\n{cmd_content}",
                tags=["command", cmd_type, "execution"],
                metadata={"session_id": session_id, "turn": turn_count, "command_index": cmd_idx, "status": "started"}
            )
            if self.test_mode:
                output = f"[TEST MODE] Would execute {cmd_type}:\n{cmd_content}"
                print(output)
                all_outputs.append(output)
                self.memory_manager.add_command_to_history(cmd_content, cmd_type, success=True)
                self.agent_state['commands_executed'] += 1
            else:
                try:
                    start_time = time.time()
                    if cmd_type in self.command_extractor.FILE_OP_TAGS:
                        result = await self._execute_file_operation(cmd_type, cmd_content, cmd_id)
                        all_outputs.append(f"FILE OP RESULT:\n{result}")
                        self.memory_manager.save_document(
                            f"file_op_result_{cmd_id}",
                            result,
                            tags=["file_operation", cmd_type, "result"],
                            metadata={"session_id": session_id, "turn": turn_count, "command_index": cmd_idx}
                        )
                    else:
                        stdout, stderr, code = await self.system_control.execute_command(
                            cmd_type,
                            cmd_content,
                            interactive=False,
                            timeout=command_timeout
                        )
                        self.memory_manager.add_command_to_history(cmd_content, cmd_type, code == 0)
                        execution_time = time.time() - start_time
                        combined_output = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}\nCODE: {code}\nTIME: {execution_time:.2f}s"
                        all_outputs.append(combined_output)
                        self.agent_state['commands_executed'] += 1
                        self.memory_manager.save_document(
                            f"command_result_{cmd_id}",
                            combined_output,
                            tags=["command", cmd_type, "result", "success" if code == 0 else "failure"],
                            metadata={"session_id": session_id, "turn": turn_count, "command_index": cmd_idx}
                        )
                        if code != 0:
                            logger.warning(f"Command failed with exit code {code}")
                            command_execution_errors += 1
                            if "timed out" in stderr.lower():
                                all_outputs.append(f"\nCommand timed out after {command_timeout}s.")
                            if command_execution_errors >= max_command_errors:
                                all_outputs.append("Too many command errors. Review approach.")
                                break
                except asyncio.TimeoutError:
                    msg = f"Command timed out after {command_timeout} seconds"
                    logger.error(msg)
                    all_outputs.append(f"ERROR: {msg}")
                    command_execution_errors += 1
                except Exception as cmd_error:
                    err_msg = f"ERROR executing {cmd_type}: {cmd_error}"
                    logger.error(err_msg)
                    all_outputs.append(err_msg)
                    command_execution_errors += 1
                    self.memory_manager.save_document(
                        f"command_error_{cmd_id}",
                        f"Error executing command:\n{err_msg}\nCommand was:\n{cmd_content}",
                        tags=["command", cmd_type, "error"],
                        metadata={"session_id": session_id, "turn": turn_count, "command_index": cmd_idx}
                    )
                    if command_execution_errors >= max_command_errors:
                        all_outputs.append("Too many command errors encountered.")
                        break
            if self.should_exit:
                break
        return all_outputs

    async def _execute_file_operation(self, op_type: str, content: str, cmd_id: str) -> str:
        try:
            params = self._parse_file_operation_params(content)
            if op_type == 'view':
                file_path = params.get('file_path', '')
                offset = int(params.get('offset', '0'))
                limit = int(params.get('limit', '2000'))
                if not file_path:
                    return "Error: Missing file_path"
                return await self.system_control.view_file(file_path, offset, limit)
            elif op_type == 'edit':
                fp = params.get('file_path', '')
                old_str = params.get('old_string', '')
                new_str = params.get('new_string', '')
                if not fp:
                    return "Error: Missing file_path"
                return await self.system_control.edit_file(fp, old_str, new_str)
            elif op_type == 'replace':
                fp = params.get('file_path', '')
                c = params.get('content', '')
                if not fp:
                    return "Error: Missing file_path"
                return await self.system_control.replace_file(fp, c)
            elif op_type == 'glob':
                pat = params.get('pattern', '')
                p = params.get('path', None)
                if not pat:
                    return "Error: Missing pattern"
                results = await self.system_control.glob_search(pat, p)
                return "\n".join(results) if isinstance(results, list) else str(results)
            elif op_type == 'grep':
                pat = params.get('pattern', '')
                inc = params.get('include', None)
                p = params.get('path', None)
                if not pat:
                    return "Error: Missing pattern"
                results = await self.system_control.grep_search(pat, inc, p)
                if isinstance(results, list):
                    out_lines = []
                    for item in results:
                        if 'error' in item:
                            out_lines.append(f"ERROR: {item['error']}")
                        elif 'message' in item:
                            out_lines.append(item['message'])
                        elif 'file' in item and 'line_number' in item:
                            out_lines.append(f"{item['file']}:{item['line_number']}: {item['line']}")
                        else:
                            out_lines.append(str(item))
                    return "\n".join(out_lines)
                return str(results)
            elif op_type == 'ls':
                path = params.get('path', '')
                if not path:
                    return "Error: Missing path"
                result = await self.system_control.list_directory(path)
                if 'error' in result:
                    return f"ERROR: {result['error']}"
                formatted = [f"Directory: {result.get('path', '')}"]
                if result.get('directories'):
                    formatted.append("\nDirectories:")
                    for d in result['directories']:
                        formatted.append(f"  {d}/")
                if result.get('files'):
                    formatted.append("\nFiles:")
                    for f_info in result['files']:
                        name = f_info.get('name', '')
                        size = f_info.get('size', 0)
                        size_str = f"{size} bytes"
                        if size >= 1024*1024:
                            size_str = f"{size/(1024*1024):.2f} MB"
                        elif size >= 1024:
                            size_str = f"{size/1024:.2f} KB"
                        formatted.append(f"  {name} ({size_str})")
                return "\n".join(formatted)
            else:
                return f"Error: Unsupported file operation: {op_type}"
        except Exception as e:
            logger.error(f"Error executing file op {op_type}: {str(e)}")
            return f"Error: {str(e)}"

    def _parse_file_operation_params(self, content: str) -> Dict[str, str]:
        params = {}
        try:
            if content.strip().startswith('{') and content.strip().endswith('}'):
                params = json.loads(content)
                return params
        except:
            pass
        lines = content.split('\n')
        current_param = None
        current_value = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^([a-zA-Z_]+)\s*:\s*(.*)$', line)
            if match:
                if current_param:
                    params[current_param] = '\n'.join(current_value).strip()
                current_param = match.group(1)
                current_value = [match.group(2)]
            else:
                if current_param:
                    current_value.append(line)
        if current_param:
            params[current_param] = '\n'.join(current_value).strip()
        return params

    async def _generate_final_reflection(self, session_id: str, turn_count: int) -> None:
        try:
            reflection_parts = [f"# Final Reflection - {session_id}", f"Generated at: {datetime.now().isoformat()}"]
            reflection_parts.append(f"Total turns: {turn_count}")
            reflection_parts.append(f"Commands executed: {self.agent_state.get('commands_executed', 0)}")
            reflection_path = self.memory_path / "reflections" / f"session_{session_id}.md"
            reflection_content = "\n".join(reflection_parts)
            with open(reflection_path, 'w') as f:
                f.write(reflection_content)
            self.memory_manager.save_document(
                f"reflection_{session_id}",
                reflection_content,
                tags=["reflection", "session", "permanent"],
                permanent=True,
                metadata={"session_id": session_id, "turn_count": turn_count}
            )
            logger.info(f"Final reflection for session {session_id}")
        except Exception as e:
            logger.error(f"Error final reflection: {e}")

    async def _request_user_input(self, question: str) -> str:
        try:
            if 'user_interactions' not in self.working_memory:
                self.working_memory['user_interactions'] = []
            self.working_memory['user_interactions'].append({'timestamp': time.time(), 'question': question})
            print("\n==================================================")
            print("AGENT REQUESTING USER INPUT:")
            print(question)
            print("Enter your response (blank line to finish):")
            lines = []
            while True:
                try:
                    line = input()
                    if not line.strip():
                        break
                    lines.append(line)
                except EOFError:
                    break
            user_input = "\n".join(lines)
            if not user_input.strip():
                user_input = "(No input provided)"
            self.working_memory['user_interactions'][-1]['response'] = user_input
            print("Continuing execution...\n")
            logger.info("User input received")
            return user_input
        except Exception as e:
            logger.error(f"Error getting user input: {e}")
            return "Error processing your input."

    async def _process_reasoning_blocks(self, response: str, session_id: str, turn_count: int) -> None:
        try:
            reasoning_data = {}
            for tag_name, extractor_method in [
                ("thinking", self.command_extractor.extract_thinking),
                ("decision", self.command_extractor.extract_decision),
                ("plan", self.command_extractor.extract_plan),
                ("summary", self.command_extractor.extract_summary),
                ("task", self.command_extractor.extract_tasks),
                ("subtask", self.command_extractor.extract_subtasks)
            ]:
                blocks = extractor_method(response)
                if blocks:
                    reasoning_data[tag_name] = blocks
                    self.memory_manager.save_document(
                        f"{tag_name}_{session_id}_{turn_count}",
                        "\n\n".join(blocks),
                        tags=[tag_name, "reasoning", "chain_of_thought"],
                        metadata={"session_id": session_id, "turn": turn_count}
                    )
                    if tag_name == "thinking":
                        self.reflections.append({"type": "thinking","content": "\n\n".join(blocks),"turn": turn_count})
                    elif tag_name == "plan":
                        self.planned_steps.append({"content": "\n\n".join(blocks),"turn": turn_count,"completed": False})
                    elif tag_name == "summary" and blocks:
                        self.executive_summary = blocks[0]
                    elif tag_name == "task":
                        for task_content in blocks:
                            lines = task_content.split('\n')
                            task_title = lines[0].strip()
                            task_details = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ""
                            task_id = f"task_{int(time.time())}_{hash(task_title) % 10000}"
                            self.task_manager.add_task(
                                task_id=task_id,
                                title=task_title,
                                description=task_details,
                                session_id=session_id,
                                metadata={"created_at": time.time(),"status": "pending"}
                            )
                    elif tag_name == "subtask" and reasoning_data.get("task"):
                        if 'tasks' in self.working_memory and self.working_memory['tasks']:
                            parent_task_id = self.working_memory['tasks'][-1]["id"]
                            for subtask_content in blocks:
                                sub_lines = subtask_content.split('\n')
                                subtask_title = sub_lines[0].strip()
                                subtask_details = '\n'.join(sub_lines[1:]).strip() if len(sub_lines) > 1 else ""
                                subtask_id = f"subtask_{int(time.time())}_{hash(subtask_title) % 10000}"
                                self.task_manager.add_subtask(
                                    parent_id=parent_task_id,
                                    subtask_id=subtask_id,
                                    title=subtask_title,
                                    description=subtask_details
                                )
            if reasoning_data:
                if 'reasoning_history' not in self.working_memory:
                    self.working_memory['reasoning_history'] = []
                self.working_memory['reasoning_history'].append({
                    "turn": turn_count,
                    "timestamp": time.time(),
                    "data": reasoning_data
                })
                if len(self.working_memory['reasoning_history']) > 5:
                    self.working_memory['reasoning_history'] = self.working_memory['reasoning_history'][-5:]
        except Exception as e:
            logger.error(f"Error processing reasoning blocks: {e}")
