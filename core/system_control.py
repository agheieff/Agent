import subprocess
import os
import pwd
import asyncio
from typing import Tuple, Optional

class SystemControl:
    def __init__(self, user: str = None):
        self.user = user
        # Only try to get uid/gid if user is specified
        if user:
            try:
                import pwd
                self.uid = pwd.getpwnam(user).pw_uid
                self.gid = pwd.getpwnam(user).pw_gid
            except (ImportError, KeyError) as e:
                print(f"Warning: Could not set up user permissions ({e}), running as current user")
                self.uid = None
                self.gid = None
        else:
            self.uid = None
            self.gid = None

    async def execute_command(self, command: str) -> Tuple[str, str, int]:
        """Execute a shell command with better error handling"""
        print(f"Executing command: {command}")  # Debug output
        try:
            # Only use preexec_fn if we have uid/gid
            kwargs = {}
            if self.uid is not None and self.gid is not None:
                kwargs['preexec_fn'] = self._switch_user
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs
            )
            
            stdout, stderr = await process.communicate()
            
            # Debug output
            print(f"Command completed with return code: {process.returncode}")
            if stdout:
                print(f"stdout: {stdout.decode()[:200]}...")
            if stderr:
                print(f"stderr: {stderr.decode()}")
            
            return (
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
                process.returncode
            )
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            print(error_msg)  # Debug output
            return "", error_msg, 1

    def _switch_user(self):
        """Switch to the AI agent user before executing commands"""
        if self.uid is not None and self.gid is not None:
            try:
                os.setgid(self.gid)
                os.setuid(self.uid)
            except PermissionError as e:
                print(f"Warning: Could not switch user ({e}), running as current user")

# Now update the relevant part in agent.py:

class AutonomousAgent:
    def __init__(self, api_key: Optional[str] = None, system_user: Optional[str] = None):
        self.llm = AnthropicClient(api_key)
        self.memory = MemoryManager()
        self.system = SystemControl(user=system_user)  # Make system_user optional
        self.current_conversation_id = None
        self.logger = logger
        self.scheduler = AsyncIOScheduler()
        self.http_session = None
        self.token_count = 0
        self.cost_limit = None
        self.initialize_agent()

    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute a system command with enhanced logging"""
        self.logger.info(f"Executing command: {command}")
        try:
            result = await self.system.execute_command(command)
            self.logger.info(f"Command completed with code: {result[2]}")
            if result[0]:  # stdout
                self.logger.info(f"Command output: {result[0][:200]}...")
            if result[1]:  # stderr
                self.logger.warning(f"Command stderr: {result[1]}")
            return result
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            self.logger.error(error_msg)
            return "", error_msg, 1

    async def think_and_act(self, prompt: str, system: str) -> str:
        """Process a thought and execute any necessary actions with improved logging"""
        if not self.current_conversation_id:
            self.start_conversation()

        # Load conversation history
        history = self.memory.load_conversation(self.current_conversation_id)
        
        # Add user prompt to history
        history.append({"role": "user", "content": prompt})
        
        # Get initial response
        response = await self.llm.get_response(prompt, system, history)
        if not response:
            error_msg = "Failed to get LLM response"
            self.logger.error(error_msg)
            return error_msg

        # Extract any commands
        commands = self.extract_commands(response)
        self.logger.info(f"Extracted commands: {commands}")
        
        # Save the initial response to history
        history.append({"role": "assistant", "content": response})
        
        if commands:
            # Execute each command and get immediate feedback
            command_responses = []
            for cmd in commands:
                self.logger.info(f"Executing command: {cmd}")
                stdout, stderr, code = await self.execute(cmd)
                
                # Format command result
                result = f"\nCommand: {cmd}\nOutput:\n{stdout}"
                if stderr:
                    result += f"\nErrors:\n{stderr}"
                result += f"\nExit code: {code}"
                command_responses.append(result)
                
                # Add command result to history
                history.append({
                    "role": "system",
                    "content": result
                })
            
            # Save conversation state
            self.memory.save_conversation(self.current_conversation_id, history)
            
            # Return full response with command outputs
            return response + "\n" + "\n".join(command_responses)
        else:
            # No commands to execute, just save the conversation
            self.memory.save_conversation(self.current_conversation_id, history)
            return response
