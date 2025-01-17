# core/agent.py
import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import ClientSession
from core.llm_client import AnthropicClient
from core.memory_manager import MemoryManager
from core.system_control import SystemControl

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class AutonomousAgent:
    def __init__(self, api_key: Optional[str] = None, system_user: str = 'claude'):
        self.llm = AnthropicClient(api_key)
        self.memory = MemoryManager()
        self.system = SystemControl(user=system_user)
        self.current_conversation_id = None
        self.logger = logger
        self.scheduler = AsyncIOScheduler()
        self.http_session = None
        self.token_count = 0
        self.cost_limit = None
        self.initialize_agent()

    def initialize_agent(self):
        """Initialize agent with enhanced capabilities"""
        self.scheduler.start()
        self.setup_persistent_storage()
        self.setup_task_scheduling()
        self.setup_cost_monitoring()

    def setup_persistent_storage(self):
        """Set up persistent storage directories"""
        storage_paths = [
            'memory/tasks',
            'memory/logs',
            'memory/metrics',
            'memory/web',
            'memory/context',
            'memory/conversations',
            'memory/docs',
            'memory/config'
        ]
        for path in storage_paths:
            os.makedirs(path, exist_ok=True)

    def setup_task_scheduling(self):
        """Initialize task scheduler with maintenance tasks"""
        self.scheduler.add_job(
            self.cleanup_old_conversations,
            'interval',
            hours=24
        )
        self.scheduler.add_job(
            self.monitor_system_resources,
            'interval',
            minutes=30
        )

    def setup_cost_monitoring(self):
        """Initialize API cost monitoring"""
        self.token_count = self.load_token_count()

    def start_conversation(self) -> str:
        """Start a new conversation and return its ID"""
        self.current_conversation_id = self.memory.create_conversation()
        return self.current_conversation_id

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results"""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            self.logger.info(f"Command result: {result[2]}")
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return "", str(e), 1

    async def think_and_act(self, prompt: str, system: str) -> str:
    """Process a thought and execute any necessary actions"""
    if not self.current_conversation_id:
        self.start_conversation()

    # Force initial command execution to prove system access
    if not self.memory.load_conversation(self.current_conversation_id):
        initial_cmd = "whoami && pwd && ps aux | grep python"
        stdout, stderr, code = await self.execute(initial_cmd)
        
        # Add the command execution to history with correct role
        history = [{
            "role": "assistant",  # Changed from "system" to "assistant"
            "content": f"Command executed: {initial_cmd}\nOutput:\n{stdout}\nError:\n{stderr}"
        }]
        self.memory.save_conversation(self.current_conversation_id, history)
        
        # Modify prompt to include the proof
        prompt = f"""System access verified with command execution:
Command: {initial_cmd}
Output: {stdout}
Error: {stderr}

Original prompt:
{prompt}"""

    # Load conversation history
    history = self.memory.load_conversation(self.current_conversation_id)
    
    # Get LLM response
    self.logger.info("Getting LLM response")
    response = await self.llm.get_response(prompt, system, history)
    
    if not response:
        self.logger.error("Failed to get LLM response")
        return "Failed to process request"

    # Save conversation history with correct roles
    history.extend([
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": response}
    ])
    self.memory.save_conversation(self.current_conversation_id, history)

    # Extract and execute commands
    commands = self.extract_commands(response)
    if commands:
        results = []
        for cmd in commands:
            stdout, stderr, code = await self.execute(cmd)
            result = {
                'command': cmd,
                'stdout': stdout,
                'stderr': stderr,
                'code': code,
                'timestamp': datetime.now().isoformat()
            }
            results.append(result)
            
            # Save command results to conversation with correct role
            history.append({
                "role": "assistant",  # Changed from "system" to "assistant"
                "content": f"Command execution result:\n{str(result)}"
            })
        
        self.memory.save_conversation(self.current_conversation_id, history)
        
        # Get LLM's analysis of the results
        result_prompt = f"Command execution results:\n{str(results)}\n\nPlease analyze these results and determine next steps."
        analysis = await self.llm.get_response(result_prompt, system, history)
        
        if analysis:
            history.append({
                "role": "assistant",
                "content": analysis
            })
            self.memory.save_conversation(self.current_conversation_id, history)
            response += f"\n\nAnalysis of results:\n{analysis}"
        
    return response

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from the response"""
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_block = []
        current_language = None
        
        for line in lines:
            stripped = line.strip()
            
            if stripped.startswith('```'):
                if in_code_block:
                    if current_language in ['bash', 'shell', 'sh', None]:
                        block_text = '\n'.join(current_block).strip()
                        if block_text:
                            block_commands = [cmd.strip() for cmd in block_text.split('\n') if cmd.strip()]
                            commands.extend(block_commands)
                    current_block = []
                    in_code_block = False
                    current_language = None
                else:
                    in_code_block = True
                    if len(stripped) > 3:
                        current_language = stripped[3:].strip().lower()
            elif in_code_block:
                current_block.append(line)
                
        self.logger.info(f"Extracted {len(commands)} commands: {commands}")
        return commands

    async def analyze_conversation(self, conversation_id: Optional[str] = None) -> str:
        """Analyze the conversation history and provide insights"""
        conv_id = conversation_id or self.current_conversation_id
        if not conv_id:
            return "No conversation to analyze"
            
        history = self.memory.load_conversation(conv_id)
        if not history:
            return "Conversation history is empty"
            
        analysis_prompt = """Please analyze this conversation history and provide insights on:
        1. Key decisions and actions taken
        2. Success rate of executed commands
        3. Overall progress toward goals
        4. Potential areas for improvement
        """
        
        analysis = await self.llm.get_response(analysis_prompt, "", history)
        return analysis

    async def setup_web_server(self, host: str = 'localhost', port: int = 8080):
        """Set up a web server for external interaction"""
        from aiohttp import web
        
        async def handle_message(request):
            try:
                data = await request.json()
                response = await self.think_and_act(data.get('message', ''), data.get('system', ''))
                return web.json_response({
                    'response': response,
                    'conversation_id': self.current_conversation_id
                })
            except Exception as e:
                return web.json_response({
                    'error': str(e)
                }, status=500)
        
        async def handle_system_status(request):
            try:
                stdout, stderr, code = await self.execute('uptime && free -h && df -h')
                return web.json_response({
                    'status': 'running',
                    'system_info': stdout,
                    'error': stderr if stderr else None
                })
            except Exception as e:
                return web.json_response({
                    'error': str(e)
                }, status=500)
        
        app = web.Application()
        app.router.add_post('/message', handle_message)
        app.router.add_get('/status', handle_system_status)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        
        self.logger.info(f"Web server started on {host}:{port}")

    async def initialize_with_prompt(self, prompt: str) -> Tuple[str, str]:
        """Initialize a new conversation with a custom prompt"""
        conv_id = self.start_conversation()
        response = await self.think_and_act(prompt, '')
        return conv_id, response

    async def monitor_system_resources(self):
        """Monitor system resource usage"""
        cmd = "top -b -n 1 | head -n 20"
        stdout, stderr, code = await self.execute(cmd)
        self.logger.info(f"System resources:\n{stdout}")

    def cleanup_old_conversations(self):
        """Clean up old conversation files to manage storage"""
        # TODO: Implement cleanup of conversations older than X days
        pass

    def save_token_count(self):
        """Save the current token count to persistent storage"""
        with open('memory/metrics/token_count.txt', 'w') as f:
            f.write(str(self.token_count))

    def load_token_count(self) -> int:
        """Load the current token count from persistent storage"""
        try:
            with open('memory/metrics/token_count.txt', 'r') as f:
                return int(f.read().strip())
        except FileNotFoundError:
            return 0

    def save_context(self, context_id: str, data: Dict):
        """Save context data to persistent storage"""
        file_path = f'memory/context/{context_id}.json'
        with open(file_path, 'w') as f:
            json.dump(data, f)

    def load_context(self, context_id: str) -> Optional[Dict]:
        """Load context data from persistent storage"""
        file_path = f'memory/context/{context_id}.json'
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return None
