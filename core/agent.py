# core/agent.py
import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from pathlib import Path
from aiohttp import web, ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
        self.logger.info("Agent initialized successfully.")

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
        self.logger.info("Persistent storage directories created.")

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
        self.logger.info("Scheduled tasks initialized.")

    def setup_cost_monitoring(self):
        """Initialize API cost monitoring"""
        self.token_count = self.load_token_count()
        self.logger.info(f"Token count loaded: {self.token_count}")

    def start_conversation(self) -> str:
        """Start a new conversation and return its ID"""
        self.current_conversation_id = self.memory.create_conversation()
        self.logger.info(f"New conversation started with ID: {self.current_conversation_id}")
        return self.current_conversation_id

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command and return the results"""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            self.logger.info(f"Command executed successfully. Exit code: {result[2]}")
            self.logger.debug(f"Command output (stdout): {result[0]}")
            self.logger.debug(f"Command output (stderr): {result[1]}")
            return result
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return "", str(e), 1

    def extract_commands(self, response: str) -> List[str]:
        """Extract commands from code blocks in the response"""
        commands = []
        lines = response.split('\n')
        in_code_block = False
        current_block = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('```'):
                if in_code_block:
                    # End of code block
                    block_text = '\n'.join(current_block).strip()
                    if block_text:
                        commands.extend([cmd.strip() for cmd in block_text.split('\n') if cmd.strip()])
                    current_block = []
                    in_code_block = False
                else:
                    # Start of code block
                    in_code_block = True
                continue
            elif in_code_block and stripped:
                current_block.append(stripped)

        # Handle any unclosed code block
        if in_code_block and current_block:
            block_text = '\n'.join(current_block).strip()
            if block_text:
                commands.extend([cmd.strip() for cmd in block_text.split('\n') if cmd.strip()])

        self.logger.debug(f"Extracted commands: {commands}")
        return [cmd for cmd in commands if cmd]

    async def think_and_act(self, prompt: str, system: str) -> str:
        """Process thoughts and commands in a continuous loop"""
        if not self.current_conversation_id:
            self.start_conversation()

        # Load or initialize conversation history
        history = self.memory.load_conversation(self.current_conversation_id)
        self.logger.info(f"Loaded conversation history: {len(history)} messages")

        # Add initial prompt only once
        if not history:
            history.append({"role": "user", "content": prompt})
            self.logger.info("Added initial prompt to conversation history.")

        while True:
            # Get Claude's response based on full history
            self.logger.info("Requesting response from LLM...")
            response = await self.llm.get_response("", system, history)
            if not response:
                self.logger.error("Failed to get LLM response.")
                return "Failed to get LLM response"

            # Save Claude's response
            history.append({"role": "assistant", "content": response})
            self.logger.info("LLM response added to conversation history.")

            # Extract commands from response
            commands = self.extract_commands(response)
            self.logger.info(f"Extracted {len(commands)} commands from LLM response.")

            # If no commands, conversation is complete
            if not commands:
                self.memory.save_conversation(self.current_conversation_id, history)
                self.logger.info("No commands found. Ending conversation.")
                return response

            # Execute all commands and add results to history
            for cmd in commands:
                self.logger.info(f"Executing command: {cmd}")
                stdout, stderr, code = await self.execute(cmd)

                # Add raw command output to history
                history.append({
                    "role": "system",
                    "content": stdout if stdout else stderr
                })
                self.logger.info("Command output added to conversation history.")

            # Save state and continue loop
            self.memory.save_conversation(self.current_conversation_id, history)
            self.logger.info("Conversation history saved.")

    async def setup_web_interface(self, host: str = '0.0.0.0', port: int = 8080):
        """Set up a web interface for monitoring and interaction"""
        routes = web.RouteTableDef()

        # Serve static HTML for the dashboard
        @routes.get('/')
        async def dashboard(request):
            self.logger.debug("Serving dashboard page.")
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>AI Agent Dashboard</title>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
                    .container { max-width: 1200px; margin: 0 auto; }
                    .card { background: #fff; padding: 20px; margin: 10px 0; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
                    .header { background: #f5f5f5; padding: 10px; margin-bottom: 20px; border-radius: 5px; }
                    .conversation { margin: 10px 0; padding: 10px; border-left: 3px solid #007bff; }
                    .status { display: inline-block; padding: 5px 10px; border-radius: 3px; margin: 5px; }
                    .status.ok { background: #28a745; color: white; }
                    .status.error { background: #dc3545; color: white; }
                    pre { background: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; }
                    .message-form { margin-top: 20px; }
                    .message-input { width: 100%; padding: 10px; margin-bottom: 10px; }
                    .submit-btn { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 3px; cursor: pointer; }
                    .submit-btn:hover { background: #0056b3; }
                </style>
                <script>
                    function refreshStatus() {
                        fetch('/status')
                            .then(response => response.json())
                            .then(data => {
                                document.getElementById('system-status').innerHTML = `
                                    <h3>System Status</h3>
                                    <pre>${data.system_info || 'No system info available'}</pre>
                                    ${data.error ? `<div class="status error">Error: ${data.error}</div>` : ''}
                                `;
                            });
                    }

                    function refreshConversation() {
                        fetch('/conversation')
                            .then(response => response.json())
                            .then(data => {
                                document.getElementById('conversation-history').innerHTML = data.messages.map(msg => `
                                    <div class="conversation">
                                        <strong>${msg.role}:</strong>
                                        <pre>${msg.content}</pre>
                                    </div>
                                `).join('');
                            });
                    }

                    function sendMessage() {
                        const message = document.getElementById('message-input').value;
                        fetch('/message', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({message})
                        })
                        .then(response => response.json())
                        .then(data => {
                            document.getElementById('message-input').value = '';
                            refreshConversation();
                        });
                    }

                    // Refresh status and conversation every 5 seconds
                    setInterval(refreshStatus, 5000);
                    setInterval(refreshConversation, 5000);

                    // Initial load
                    document.addEventListener('DOMContentLoaded', () => {
                        refreshStatus();
                        refreshConversation();
                    });
                </script>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>AI Agent Dashboard</h1>
                        <div class="status ok">Active</div>
                    </div>

                    <div class="card" id="system-status">
                        <h3>System Status</h3>
                        <p>Loading...</p>
                    </div>

                    <div class="card">
                        <h3>Conversation</h3>
                        <div id="conversation-history">
                            <p>Loading conversation history...</p>
                        </div>

                        <div class="message-form">
                            <textarea id="message-input" class="message-input" rows="4" placeholder="Type your message here..."></textarea>
                            <button onclick="sendMessage()" class="submit-btn">Send Message</button>
                        </div>
                    </div>
                </div>
            </body>
            </html>
            """
            return web.Response(text=html, content_type='text/html')

        @routes.get('/status')
        async def status(request):
            self.logger.debug("Handling /status request.")
            stdout, stderr, code = await self.execute('uptime && free -h && df -h')
            return web.json_response({
                'status': 'active',
                'system_info': stdout,
                'error': stderr if stderr else None
            })

        @routes.get('/conversation')
        async def get_conversation(request):
            self.logger.debug("Handling /conversation request.")
            history = self.memory.load_conversation(self.current_conversation_id)
            return web.json_response({
                'conversation_id': self.current_conversation_id,
                'messages': history
            })

        @routes.post('/message')
        async def handle_message(request):
            try:
                self.logger.debug("Handling /message request.")
                data = await request.json()
                response = await self.think_and_act(data.get('message', ''), '')
                return web.json_response({
                    'response': response,
                    'conversation_id': self.current_conversation_id
                })
            except Exception as e:
                self.logger.error(f"Error handling /message request: {e}")
                return web.json_response({
                    'error': str(e)
                }, status=500)

        app = web.Application()
        app.add_routes(routes)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        self.logger.info(f"Web interface started on http://{host}:{port}")

    async def run(self, host: str = '0.0.0.0', port: int = 8080):
        """Main method to run the agent with web interface"""
        try:
            # Start web interface
            await self.setup_web_interface(host=host, port=port)

            # Keep the agent running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down agent...")
            self.scheduler.shutdown()
        except Exception as e:
            self.logger.error(f"Error running agent: {e}")
            raise
