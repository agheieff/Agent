import asyncio
import logging
import re
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
import json

logger = logging.getLogger(__name__)

class ShellTranspiler:
    """Converts between Nu shell and Bash commands"""
    
    NU_TO_BASH_MAPPINGS = {
        # Basic commands
        r'ls\s*$': 'ls',
        r'ls\s+(.+)': r'ls \1',
        r'pwd': 'pwd',
        r'cd\s+(.+)': r'cd \1',
        
        # Data manipulation
        r'where\s+(.+)': r'grep \1',
        r'select\s+(.+)': r'cut -f \1',
        r'sort-by\s+(.+)': r'sort -k \1',
        
        # File operations
        r'rm\s+(.+)': r'rm \1',
        r'cp\s+(.+)\s+(.+)': r'cp \1 \2',
        r'mv\s+(.+)\s+(.+)': r'mv \1 \2',
        
        # Advanced operations
        r'open\s+(.+)': r'cat \1',
        r'save\s+(.+)': r'> \1',
    }
    
    BASH_TO_NU_MAPPINGS = {
        # Reverse mappings
        r'grep\s+(.+)': r'where \1',
        r'cut -f\s+(.+)': r'select \1',
        r'sort -k\s+(.+)': r'sort-by \1',
        r'cat\s+(.+)': r'open \1',
        r'>\s+(.+)': r'save \1',
    }
    
    def to_bash(self, nu_command: str) -> str:
        """Convert Nu shell command to Bash"""
        for pattern, replacement in self.NU_TO_BASH_MAPPINGS.items():
            match = re.match(pattern, nu_command)
            if match:
                return re.sub(pattern, replacement, nu_command)
        return nu_command  # Return original if no mapping found
    
    def to_nu(self, bash_command: str) -> str:
        """Convert Bash command to Nu shell"""
        for pattern, replacement in self.BASH_TO_NU_MAPPINGS.items():
            match = re.match(pattern, bash_command)
            if match:
                return re.sub(pattern, replacement, bash_command)
        return bash_command  # Return original if no mapping found

class ShellAdapter:
    """Hybrid shell adapter supporting both Nu shell and Bash"""
    
    def __init__(self, preferred_shell: str = 'nu'):
        self.preferred_shell = preferred_shell
        self.transpiler = ShellTranspiler()
        self.command_history: List[Dict] = []
        self.working_dir = Path.cwd()
        
    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute command in preferred shell with automatic transpilation"""
        try:
            # Prepare command based on shell preference
            if self.preferred_shell == 'nu':
                if self._is_bash_specific(command):
                    exec_command = command  # Use bash for bash-specific commands
                    shell = 'bash'
                else:
                    exec_command = command  # Already in Nu format
                    shell = 'nu'
            else:  # bash is preferred
                if self._is_nu_specific(command):
                    exec_command = self.transpiler.to_bash(command)
                    shell = 'bash'
                else:
                    exec_command = command
                    shell = 'bash'
            
            # Execute command
            process = await asyncio.create_subprocess_shell(
                exec_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={'SHELL': f'/bin/{shell}'}
            )
            
            stdout, stderr = await process.communicate()
            
            # Store command history
            self.command_history.append({
                'command': command,
                'shell': shell,
                'executed_as': exec_command,
                'stdout': stdout.decode() if stdout else "",
                'stderr': stderr.decode() if stderr else "",
                'code': process.returncode
            })
            
            return (
                stdout.decode() if stdout else "",
                stderr.decode() if stderr else "",
                process.returncode
            )
            
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg)
            return "", error_msg, 1
    
    def _is_bash_specific(self, command: str) -> bool:
        """Check if command is bash-specific"""
        bash_patterns = [
            r'.*\|\|.*',  # Bash OR operator
            r'.*&&.*',    # Bash AND operator
            r'.*>[^|].*', # Bash output redirection
            r'.*<.*',     # Bash input redirection
            r'.*\$\(.*\).*', # Bash command substitution
            r'.*`.*`.*',  # Backtick command substitution
            r'.*\{\}.*',  # Bash brace expansion
            r'.*\[\[.*\]\].*', # Bash test command
        ]
        return any(re.match(pattern, command) for pattern in bash_patterns)
    
    def _is_nu_specific(self, command: str) -> bool:
        """Check if command is Nu shell-specific"""
        nu_patterns = [
            r'.*\|>\s+\w+.*',  # Nu pipeline to variable
            r'.*\|\s+where.*',  # Nu where filter
            r'.*\|\s+select.*', # Nu select columns
            r'.*\|\s+sort-by.*', # Nu sort-by
        ]
        return any(re.match(pattern, command) for pattern in nu_patterns)
    
    def get_command_history(self) -> List[Dict]:
        """Get command execution history"""
        return self.command_history
    
    def clear_history(self):
        """Clear command history"""
        self.command_history = [] 