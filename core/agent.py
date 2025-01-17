"""
core/enhanced_agent.py - Enhanced version of the autonomous agent with additional capabilities
"""
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

class EnhancedAutonomousAgent(AutonomousAgent):
    def __init__(self, api_key: Optional[str] = None, system_user: str = 'claude'):
        super().__init__(api_key, system_user)
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
        """Set up enhanced persistent storage"""
        storage_paths = [
            'memory/tasks',
            'memory/logs',
            'memory/metrics',
            'memory/web',
            'memory/context'
        ]
        for path in storage_paths:
            os.makedirs(path, exist_ok=True)

    def setup_task_scheduling(self):
        """Initialize task scheduler with common maintenance tasks"""
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
        
    async def initialize_with_prompt(self, prompt: str) -> str:
        """Initialize a new conversation with a custom prompt"""
        conv_id = self.start_conversation()
        system_prompt = self.load_system_prompt()
        response = await self.think_and_act(prompt, system_prompt)
        return conv_id, response

    async def schedule_task(self, task_func, trigger, **trigger_args):
        """Schedule a task with the scheduler"""
        job = self.scheduler.add_job(
            task_func,
            trigger,
            **trigger_args
        )
        self.save_scheduled_task(job.id, task_func.__name__, trigger, trigger_args)
        return job.id

    async def setup_web_server(self, port: int = 8080):
        """Set up a simple web server for external interaction"""
        from aiohttp import web
        
        async def handle_message(request):
            data = await request.json()
            response = await self.think_and_act(data['message'], data.get('system', ''))
            return web.json_response({'response': response})
            
        app = web.Application()
        app.router.add_post('/message', handle_message)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', port)
        await site.start()

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

    def load_token_count(self) -> int:
        """Load the current token count from persistent storage"""
        try:
            with open('memory/metrics/token_count.txt', 'r') as f:
                return int(f.read().strip())
        except FileNotFoundError:
            return 0

    def save_token_count(self):
        """Save the current token count to persistent storage"""
        with open('memory/metrics/token_count.txt', 'w') as f:
            f.write(str(self.token_count))

    async def monitor_system_resources(self):
        """Monitor system resource usage"""
        cmd = "top -b -n 1 | head -n 20"
        stdout, stderr, code = await self.execute(cmd)
        self.logger.info(f"System resources:\n{stdout}")

    def cleanup_old_conversations(self):
        """Clean up old conversation files to manage storage"""
        # Implementation to remove conversations older than X days
        pass

    async def execute_with_timeout(self, command: str, timeout: int = 60) -> Tuple[str, str, int]:
        """Execute a command with timeout"""
        try:
            return await asyncio.wait_for(
                self.execute(command),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return "", "Command timed out", 1

    async def safe_think_and_act(self, prompt: str, system: str = "") -> str:
        """Wrapper for think_and_act with additional safety checks"""
        # Check API usage before proceeding
        if self.cost_limit and self.token_count >= self.cost_limit:
            return "API cost limit reached. Please check the configuration."
            
        response = await super().think_and_act(prompt, system)
        
        # Update token count (approximate)
        self.token_count += len(prompt + response) // 4
        self.save_token_count()
        
        return response

    def load_system_prompt(self) -> str:
        """Load the system prompt from configuration"""
        try:
            with open('memory/config/system_prompt.txt', 'r') as f:
                return f.read()
        except FileNotFoundError:
            return ""  # Return empty string if no custom prompt is configured
