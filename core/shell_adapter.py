import asyncio
import logging
import re
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path
import json
import subprocess
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class TranspilerError(Exception):
    """Base class for transpiler errors"""
    pass

class ConversionError(TranspilerError):
    """Error during command conversion"""
    pass

class ValidationError(TranspilerError):
    """Error during command validation"""
    pass

class ShellType(Enum):
    """Supported shell types"""
    BASH = "bash"
    NU = "nu"

@dataclass
class ConversionResult:
    """Result of command conversion"""
    success: bool
    converted_command: Optional[str] = None
    error_message: Optional[str] = None
    warnings: List[str] = None
    original_command: Optional[str] = None
    shell_type: Optional[ShellType] = None

class ShellTranspiler:
    """Enhanced shell command transpiler with comprehensive mappings"""
    
    # Comprehensive command mappings
    NU_TO_BASH_MAPPINGS = {
        # File operations
        r'ls\s*$': 'ls',
        r'ls\s+(.+)': r'ls \1',
        r'pwd': 'pwd',
        r'cd\s+(.+)': r'cd \1',
        r'rm\s+(.+)': r'rm \1',
        r'cp\s+(.+)\s+(.+)': r'cp \1 \2',
        r'mv\s+(.+)\s+(.+)': r'mv \1 \2',
        r'mkdir\s+(.+)': r'mkdir \1',
        
        # File content operations
        r'open\s+(.+)': r'cat \1',
        r'save\s+(.+)': r'> \1',
        r'append\s+(.+)': r'>> \1',
        
        # Data processing
        r'where\s+(.+)': r'grep \1',
        r'select\s+(.+)': r'cut -f \1',
        r'sort-by\s+(.+)': r'sort -k \1',
        r'uniq': 'uniq',
        r'length': 'wc -l',
        
        # Process management
        r'ps': 'ps aux',
        r'kill\s+(.+)': r'kill \1',
        r'exec\s+(.+)': r'exec \1',
        
        # Network operations
        r'fetch\s+(.+)': r'curl \1',
        r'post\s+(.+)': r'curl -X POST \1',
        r'ping\s+(.+)': r'ping \1',
        
        # System information
        r'sys': 'uname -a',
        r'df': 'df -h',
        r'du\s+(.+)': r'du -h \1',
        
        # Text processing
        r'split\s+(.+)\s+--separator\s+(.+)': r'split -d "\2" \1',
        r'str substring\s+(\d+)\s+(\d+)': r'cut -c\1-\2',
        r'str replace\s+(.+)\s+(.+)': r'sed "s/\1/\2/g"',
        
        # Archive operations
        r'tar list\s+(.+)': r'tar -tvf \1',
        r'tar extract\s+(.+)': r'tar -xf \1',
        r'zip\s+(.+)': r'gzip \1',
        r'unzip\s+(.+)': r'gunzip \1'
    }
    
    BASH_TO_NU_MAPPINGS = {
        # Reverse mappings
        r'grep\s+(.+)': r'where \1',
        r'cut -f\s+(.+)': r'select \1',
        r'sort -k\s+(.+)': r'sort-by \1',
        r'cat\s+(.+)': r'open \1',
        r'>\s+(.+)': r'save \1',
        r'>>\s+(.+)': r'append \1',
        r'wc -l': 'length',
        r'curl\s+(.+)': r'fetch \1',
        r'curl -X POST\s+(.+)': r'post \1',
        r'sed "s/(.+)/(.+)/g"': r'str replace \1 \2',
        r'tar -tvf\s+(.+)': r'tar list \1',
        r'tar -xf\s+(.+)': r'tar extract \1'
    }
    
    def __init__(self):
        self.command_cache: Dict[str, ConversionResult] = {}
        
    def _validate_command(self, command: str, shell_type: ShellType) -> List[str]:
        """Validate command and return warnings"""
        warnings = []
        
        # Check for unsupported features
        if shell_type == ShellType.NU:
            unsupported = [
                ('&&', 'Command chaining not supported in Nu'),
                ('||', 'OR operator not supported in Nu'),
                ('&>', 'File descriptor redirection not supported in Nu')
            ]
            for pattern, warning in unsupported:
                if pattern in command:
                    warnings.append(warning)
                    
        # Check for potential issues
        if '|' in command and shell_type == ShellType.NU:
            warnings.append('Pipe behavior may differ in Nu shell')
            
        return warnings
        
    def _check_command_availability(self, command: str, shell_type: ShellType) -> bool:
        """Check if command is available in target shell"""
        try:
            cmd_parts = command.split()
            if not cmd_parts:
                return False
                
            binary = cmd_parts[0]
            shell = 'nu' if shell_type == ShellType.NU else 'bash'
            
            result = subprocess.run(
                [shell, '-c', f'command -v {binary}'],
                capture_output=True,
                text=True
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error checking command availability: {e}")
            return False
            
    def to_bash(self, nu_command: str) -> ConversionResult:
        """Convert Nu shell command to Bash with enhanced error handling"""
        try:
            # Check cache
            cache_key = f"nu_to_bash_{nu_command}"
            if cache_key in self.command_cache:
                return self.command_cache[cache_key]
                
            # Validate input
            if not nu_command.strip():
                raise ConversionError("Empty command")
                
            # Get warnings
            warnings = self._validate_command(nu_command, ShellType.NU)
            
            # Try conversion
            converted = nu_command
            for pattern, replacement in self.NU_TO_BASH_MAPPINGS.items():
                match = re.match(pattern, nu_command)
                if match:
                    converted = re.sub(pattern, replacement, nu_command)
                    break
                    
            # Validate result
            if not self._check_command_availability(converted.split()[0], ShellType.BASH):
                warnings.append(f"Command {converted.split()[0]} may not be available in bash")
                
            result = ConversionResult(
                success=True,
                converted_command=converted,
                warnings=warnings,
                original_command=nu_command,
                shell_type=ShellType.BASH
            )
            
            # Cache result
            self.command_cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Error converting to bash: {e}")
            return ConversionResult(
                success=False,
                error_message=str(e),
                original_command=nu_command,
                shell_type=ShellType.BASH
            )
            
    def to_nu(self, bash_command: str) -> ConversionResult:
        """Convert Bash command to Nu shell with enhanced error handling"""
        try:
            # Check cache
            cache_key = f"bash_to_nu_{bash_command}"
            if cache_key in self.command_cache:
                return self.command_cache[cache_key]
                
            # Validate input
            if not bash_command.strip():
                raise ConversionError("Empty command")
                
            # Get warnings
            warnings = self._validate_command(bash_command, ShellType.BASH)
            
            # Try conversion
            converted = bash_command
            for pattern, replacement in self.BASH_TO_NU_MAPPINGS.items():
                match = re.match(pattern, bash_command)
                if match:
                    converted = re.sub(pattern, replacement, bash_command)
                    break
                    
            # Validate result
            if not self._check_command_availability(converted.split()[0], ShellType.NU):
                warnings.append(f"Command {converted.split()[0]} may not be available in nu")
                
            result = ConversionResult(
                success=True,
                converted_command=converted,
                warnings=warnings,
                original_command=bash_command,
                shell_type=ShellType.NU
            )
            
            # Cache result
            self.command_cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Error converting to nu: {e}")
            return ConversionResult(
                success=False,
                error_message=str(e),
                original_command=bash_command,
                shell_type=ShellType.NU
            )
            
    def clear_cache(self):
        """Clear the command conversion cache"""
        self.command_cache.clear()

class ShellAdapter:
    """Hybrid shell adapter supporting both Nu shell and Bash"""
    
    def __init__(self, preferred_shell: str = 'nu'):
        self.preferred_shell = ShellType(preferred_shell)
        self.transpiler = ShellTranspiler()
        self.command_history: List[Dict] = []
        self.working_dir = Path.cwd()
        
    async def execute(self, command: str) -> Tuple[str, str, int]:
        """Execute command in preferred shell with automatic transpilation"""
        try:
            # Prepare command based on shell preference
            if self.preferred_shell == ShellType.NU:
                if self._is_bash_specific(command):
                    conversion = self.transpiler.to_nu(command)
                    if conversion.success:
                        exec_command = conversion.converted_command
                        shell = 'nu'
                    else:
                        exec_command = command
                        shell = 'bash'
                else:
                    exec_command = command
                    shell = 'nu'
            else:
                if self._is_nu_specific(command):
                    conversion = self.transpiler.to_bash(command)
                    if conversion.success:
                        exec_command = conversion.converted_command
                        shell = 'bash'
                    else:
                        exec_command = command
                        shell = 'nu'
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
            r'.*\|\s+uniq.*',   # Nu uniq
            r'.*\|\s+length.*', # Nu length
            r'.*\|\s+str\s+.*', # Nu string operations
        ]
        return any(re.match(pattern, command) for pattern in nu_patterns)
    
    def get_command_history(self) -> List[Dict]:
        """Get command execution history"""
        return self.command_history
    
    def clear_history(self):
        """Clear command history and transpiler cache"""
        self.command_history = []
        self.transpiler.clear_cache() 