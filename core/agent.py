import asyncio
import logging
import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from core.llm_client import get_llm_client
from core.memory_manager import MemoryManager
from core.system_control import SystemControl
from core.task_manager import TaskManager
from core.memory_preloader import MemoryPreloader
import networkx as nx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)

console_handler = logging.getLogger().handlers[1]
console_handler.setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class CommandResult:
    """Enhanced command execution results"""
    def __init__(self, stdout: str, stderr: str, code: int):
        self.stdout = stdout
        self.stderr = stderr
        self.code = code
        self.success = code == 0
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
    """Extracts commands from LLM responses using XML tags"""
    
    COMMAND_TAGS = ['bash', 'python']
    
    @staticmethod
    def extract_commands(response: str) -> List[Tuple[str, str]]:
        """
        Extract commands from response text using XML tags
        Returns a list of (command_type, command) tuples
        """
        commands = []
        
        for tag in CommandExtractor.COMMAND_TAGS:
            pattern = f"<{tag}>(.*?)</{tag}>"
            matches = re.finditer(pattern, response, re.DOTALL)
            
            for match in matches:
                command = match.group(1).strip()
                if command:
                    commands.append((tag, command))
        
        return commands

    @staticmethod
    def extract_heredocs(response: str) -> List[Dict[str, str]]:
        """Extract heredoc blocks from response text"""
        heredocs = []
        current_doc = None
        content_lines = []
        
        for line in response.split('\n'):
            if line.strip().startswith('cat << EOF >'):
                # Start new heredoc
                if current_doc:
                    heredocs.append({
                        'filename': current_doc,
                        'content': '\n'.join(content_lines)
                    })
                    content_lines = []
                
                # Extract filename
                current_doc = line.strip().split('>')[1].strip()
                continue
                
            if line.strip() == 'EOF' and current_doc:
                # End current heredoc
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
        """Check if command is an exit command"""
        if command_type == 'bash':
            return command.strip().lower() in ['exit', 'quit', 'bye']
        return False

class AutonomousAgent:
    def __init__(self, memory_manager, session_manager, api_key: str, model: str = "deepseek"):
        if not api_key:
            raise ValueError("API key required")

        self.memory_path = Path("memory")
        self.memory_manager = memory_manager
        self.system_control = SystemControl()
        self.task_manager = TaskManager(self.memory_path)
        self.session_manager = session_manager
        self.preloader = MemoryPreloader(memory_manager)
        
        # Then check for first-run setup
        if not (self.memory_path / "vector_index").exists():
            self.memory_manager.save_document(
                "system_guide",
                Path("config/system_prompt.md").read_text()  # Updated path
            )

        # Rest of initialization
        self.llm = get_llm_client(model, api_key)
        self.current_conversation_id = None
        self.last_session_summary = self._load_last_session()
        self.command_extractor = CommandExtractor()
        self._setup_storage()
        self.should_exit = False
        self.command_history = []
        self.heartbeat_task = None

    async def run(self, initial_prompt: str, system_prompt: str) -> None:
        """Run agent with enhanced error handling"""
        try:
            print("\nStarting agent session...")
            print("\nInitializing...")
            
            # Start heartbeat task
            self.heartbeat_task = asyncio.create_task(self.heartbeat())
            
            await self.think_and_act(initial_prompt, system_prompt)
            
            if self.should_exit:
                print("\nSession ended by agent")
            else:
                print("\nSession completed naturally")
                
        except Exception as e:
            logger.error(f"Run failed: {e}")
            raise
        finally:
            print("\nCleaning up...")
            # Cancel heartbeat task if it exists
            if self.heartbeat_task and not self.heartbeat_task.done():
                self.heartbeat_task.cancel()
                try:
                    await self.heartbeat_task
                except asyncio.CancelledError:
                    pass
            self.cleanup()

    def _setup_storage(self):
        """Ensure required directories exist"""
        dirs = [
            'conversations',
            'logs',
            'summaries',
            'config',
            'scripts',
            'data',
            'temp',
            'state'
        ]
        for dir_name in dirs:
            (self.memory_path / dir_name).mkdir(parents=True, exist_ok=True)

    def _load_system_prompt(self, path: Path) -> str:
        """Load system prompt from file"""
        try:
            with open(Path("config/system_prompt.md")) as f:  # Updated path
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"System prompt not found at {path}, using empty prompt")
            return ""

    def _load_last_session(self) -> Optional[str]:
        """Load summary of last session"""
        summary_path = self.memory_path / "summaries/last_session.txt"
        try:
            if summary_path.exists():
                with open(summary_path) as f:
                    return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading last session: {e}")
        return None

    def _save_session_summary(self, summary: str):
        """Save session summary for next run"""
        try:
            with open(self.memory_path / "summaries/last_session.txt", 'w') as f:
                f.write(summary)
        except Exception as e:
            logger.error(f"Error saving session summary: {e}")

    def print_response(self, content: str):
        """Print agent's response with clear formatting"""
        print("\n=== CLAUDE ===")
        print(content)
        print("=============")

    async def process_heredocs(self, response: str) -> None:
        """Process and save heredoc content to files"""
        heredocs = self.command_extractor.extract_heredocs(response)
        for doc in heredocs:
            try:
                filepath = Path(doc['filename'])
                filepath.parent.mkdir(parents=True, exist_ok=True)
                
                with open(filepath, 'w') as f:
                    f.write(doc['content'])
                    
                logger.info(f"Created file: {filepath}")
            except Exception as e:
                logger.error(f"Error creating file {doc['filename']}: {e}")

    async def think_and_act(self, initial_prompt: str, system_prompt: str) -> None:
        messages = []
        
        # Initialize session context
        self.preloader.initialize_session()
        
        # Add temporal context
        temporal_context = self.memory_manager.get_execution_context()
        messages.append({
            "role": "system",
            "content": f"TEMPORAL CONTEXT:\n{temporal_context}"
        })
        
        # Add system prompt
        messages.append({
            "role": "system",
            "content": system_prompt
        })
        
        # Add initial prompt
        messages.append({
            "role": "user",
            "content": initial_prompt
        })
        
        # Get active branch context if available
        if self.session_manager.current_session and self.session_manager.current_session.active_branch_id:
            branch_context = self.session_manager.get_branch_context(
                self.session_manager.current_session.active_branch_id
            )
            if branch_context:
                messages.append({
                    "role": "system",
                    "content": f"BRANCH CONTEXT:\n{json.dumps(branch_context, indent=2)}"
                })
        
        # Process command sequence with dependencies
        try:
            commands = self._parse_commands(initial_prompt)
            ordered_commands = self._resolve_dependencies(commands)
            
            for command in ordered_commands:
                result = await self._execute_command(command)
                if not result.success:
                    logger.error(f"Command execution failed: {result.error}")
                    break
                    
                # Update branch history if in a branch
                if (self.session_manager.current_session and 
                    self.session_manager.current_session.active_branch_id):
                    self.session_manager.add_command_to_branch(
                        self.session_manager.current_session.active_branch_id,
                        command.raw_command,
                        command.type,
                        result.success
                    )
        
        except Exception as e:
            logger.error(f"Error in think_and_act: {e}")
            
    def _resolve_dependencies(self, commands: List[Dict]) -> List[Dict]:
        """Resolve command dependencies using topological sort"""
        # Build dependency graph
        graph = nx.DiGraph()
        command_map = {}
        
        for i, cmd in enumerate(commands):
            cmd_id = f"cmd_{i}"
            graph.add_node(cmd_id, command=cmd)
            command_map[cmd_id] = cmd
            
            if cmd['type'] == 'task' and 'dependencies' in cmd:
                for dep in cmd['dependencies']:
                    if dep.startswith('#'):
                        # ID reference
                        dep_id = dep[1:]
                        if dep_id in command_map:
                            graph.add_edge(dep_id, cmd_id)
                    elif dep.startswith('@'):
                        # Task reference - find most recent matching task
                        task_name = dep[1:]
                        for j in range(i-1, -1, -1):
                            prev_cmd = commands[j]
                            if (prev_cmd['type'] == 'task' and 
                                prev_cmd.get('attributes', {}).get('name') == task_name):
                                prev_id = f"cmd_{j}"
                                graph.add_edge(prev_id, cmd_id)
                                break
        
        # Check for cycles
        try:
            ordered = list(nx.topological_sort(graph))
            return [command_map[cmd_id] for cmd_id in ordered]
        except nx.NetworkXUnfeasible:
            logger.error("Circular dependency detected in commands")
            return commands  # Return original order if cycle detected

    def _is_conversation_complete(self, response: str) -> bool:
        """Check if conversation is complete"""
        completion_phrases = [
            "task complete",
            "finished",
            "all done",
            "completed successfully",
            "goodbye",
            "session ended"
        ]
        return any(phrase in response.lower() for phrase in completion_phrases)

    def cleanup(self):
        """Cleanup resources and save state"""
        try:
            # Save any pending state
            if self.current_conversation_id:
                self.memory_manager.save_conversation(
                    self.current_conversation_id,
                    []  # Add any pending messages here
                )
            
            # Save command history
            history_path = self.memory_path / "state/command_history.json"
            with open(history_path, 'w') as f:
                json.dump(self.command_history, f, indent=2)
            
            # Clean up temp directory
            temp_dir = self.memory_path / "temp"
            if temp_dir.exists():
                for file in temp_dir.iterdir():
                    try:
                        file.unlink()
                    except Exception as e:
                        logger.error(f"Error cleaning up {file}: {e}")
            
            # Cleanup system control processes
            self.system_control.cleanup()
                        
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def heartbeat(self):
        """Auto-save state every 5 minutes"""
        while not self.should_exit:
            self._save_state()
            await asyncio.sleep(300)

    def _save_state(self):
        """Save critical state information"""
        state = {
            "tasks": self.task_manager.active_tasks,
            "environment": dict(os.environ),
            "last_commands": self.command_history[-5:],
            "session_summary": self.last_session_summary
        }
        self.memory_manager.save_document("system_state", json.dumps(state))

    async def compress_context(self, messages: List[Dict]) -> List[Dict]:
        """Keep conversation under 4k tokens using vector search"""
        if len(str(messages)) > 3500:
            relevant_memories = self.memory_manager.search_memory(
                "Recent important system changes"
            )
            return [{"role": "system", "content": f"Relevant memories: {relevant_memories}"}]
        return messages
