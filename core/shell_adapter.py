import asyncio
import logging
import re
from typing import Dict, List, Optional, Tuple, Union, Any
from pathlib import Path
import json
import subprocess
from dataclasses import dataclass, field
from enum import Enum
import shutil
import tempfile
import textwrap

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

@dataclass
class StructuredOutput:
    """Represents structured output from shell commands"""
    raw_output: str
    data: Any
    format_type: str = 'plain'
    schema: Optional[Dict] = None
    metadata: Dict = field(default_factory=dict)

    def to_json(self) -> str:
        """Convert to JSON representation"""
        return json.dumps({
            'data': self.data,
            'format': self.format_type,
            'schema': self.schema,
            'metadata': self.metadata
        }, indent=2)

class OutputFormat(Enum):
    """Supported output formats"""
    PLAIN = 'plain'
    TABLE = 'table'
    LIST = 'list'
    RECORD = 'record'
    JSON = 'json'

class ShellTranspiler:
    """Enhanced shell command transpiler with error recovery"""
    
    # Expanded command mappings including package management, process monitoring, etc.
    NU_TO_BASH_MAPPINGS = {
        # File operations (existing)
        r'ls\s*$': 'ls',
        r'ls\s+(.+)': r'ls \1',
        r'pwd': 'pwd',
        r'cd\s+(.+)': r'cd \1',
        
        # Package management
        r'apt\s+install\s+(.+)': r'apt-get install \1',
        r'apt\s+update': 'apt-get update',
        r'pacman\s+-S\s+(.+)': r'pacman -S \1',
        r'pacman\s+-Syu': 'pacman -Syu',
        r'winget\s+install\s+(.+)': r'winget install \1',
        
        # Process monitoring
        r'ps': 'ps aux',
        r'procs': 'ps aux',
        r'top': 'top',
        r'htop': 'htop',
        
        # Service management
        r'service\s+status\s+(.+)': r'systemctl status \1',
        r'service\s+start\s+(.+)': r'systemctl start \1',
        r'service\s+stop\s+(.+)': r'systemctl stop \1',
        r'service\s+restart\s+(.+)': r'systemctl restart \1',
        
        # Network configuration
        r'ip\s+addr': 'ip addr show',
        r'ip\s+route': 'ip route show',
        r'nmcli\s+dev\s+wifi': 'nmcli device wifi list',
        r'nmcli\s+con\s+show': 'nmcli connection show',
        
        # Additional common operations
        r'df': 'df -h',
        r'du\s+(.+)': r'du -h \1',
        r'free': 'free -h',
        r'mount': 'mount',
        r'lsblk': 'lsblk',
        r'journalctl\s+(.+)': r'journalctl \1',
        r'dmesg': 'dmesg',
        r'uname': 'uname -a',
        r'uptime': 'uptime',
        r'who': 'who',
        r'w': 'w',
        r'last': 'last',
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
    
    def __init__(self, security_manager=None):
        self.command_cache: Dict[str, ConversionResult] = {}
        self.security_manager = security_manager
        self.man_cache: Dict[str, str] = {}
        
    def _validate_command(self, command: str, shell_type: ShellType) -> List[str]:
        """Enhanced command validation with man page lookup"""
        warnings = []
        
        try:
            # Get command binary
            cmd_parts = command.split()
            if not cmd_parts:
                return ["Empty command"]
                
            binary = cmd_parts[0]
            
            # Check man page if not in cache
            if binary not in self.man_cache:
                man_result = subprocess.run(
                    ['man', binary],
                    capture_output=True,
                    text=True
                )
                if man_result.returncode == 0:
                    self.man_cache[binary] = man_result.stdout
                else:
                    warnings.append(f"No man page found for {binary}")
                    
            # Validate against man page if available
            if binary in self.man_cache:
                for arg in cmd_parts[1:]:
                    if arg.startswith('-'):
                        if arg not in self.man_cache[binary]:
                            warnings.append(f"Option {arg} not found in man page")
                            
            # Shell-specific validation
            if shell_type == ShellType.NU:
                unsupported = [
                    ('&&', 'Command chaining not supported in Nu'),
                    ('||', 'OR operator not supported in Nu'),
                    ('&>', 'File descriptor redirection not supported in Nu')
                ]
                for pattern, warning in unsupported:
                    if pattern in command:
                        warnings.append(warning)
                        
            # Security validation if manager available
            if self.security_manager:
                security_result = self.security_manager.validate_command(
                    command,
                    shell_type.value
                )
                if not security_result['is_safe']:
                    warnings.extend(security_result['warnings'])
                    
        except Exception as e:
            warnings.append(f"Validation error: {str(e)}")
            
        return warnings
        
    def _repair_command(self, command: str, shell_type: ShellType) -> Tuple[str, List[str]]:
        """Attempt to repair common command errors"""
        repairs = []
        repaired = command
        
        # Common repair patterns
        repairs_map = {
            r'\|\s*grep': '| where',  # Fix grep usage
            r'>\s*(.+)': '| save \1',  # Fix output redirection
            r'>>\s*(.+)': '| append \1',  # Fix append redirection
            r'\|\s*wc\s+-l': '| length',  # Fix line counting
            r'\|\s*sort': '| sort-by',  # Fix sorting
            r'\|\s*uniq': '| uniq',  # Fix unique
        }
        
        if shell_type == ShellType.NU:
            for pattern, replacement in repairs_map.items():
                if re.search(pattern, repaired):
                    repaired = re.sub(pattern, replacement, repaired)
                    repairs.append(f"Converted {pattern} to {replacement}")
                    
        return repaired, repairs

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

class NuOutputParser:
    """Enhanced parser for NuShell structured output"""
    
    @staticmethod
    def parse_output(output: str) -> StructuredOutput:
        """Parse NuShell output into structured format"""
        try:
            # Try parsing as JSON first
            data = json.loads(output)
            return StructuredOutput(
                raw_output=output,
                data=data,
                format_type='json'
            )
        except json.JSONDecodeError:
            # Try parsing as table
            if NuOutputParser._is_table(output):
                table_data = NuOutputParser._parse_table(output)
                return StructuredOutput(
                    raw_output=output,
                    data=table_data,
                    format_type='table',
                    schema=NuOutputParser._infer_schema(table_data)
                )
            
            # Try parsing as list
            if NuOutputParser._is_list(output):
                list_data = NuOutputParser._parse_list(output)
                return StructuredOutput(
                    raw_output=output,
                    data=list_data,
                    format_type='list'
                )
                
            # Default to plain text
            return StructuredOutput(
                raw_output=output,
                data=output,
                format_type='plain'
            )
            
    @staticmethod
    def _is_table(output: str) -> bool:
        """Check if output appears to be a table"""
        lines = output.strip().split('\n')
        if len(lines) < 2:
            return False
            
        # Check for consistent column separators
        separator_count = lines[0].count('│')
        return all(line.count('│') == separator_count for line in lines[1:])
        
    @staticmethod
    def _parse_table(output: str) -> List[Dict]:
        """Parse Nu table output into list of records"""
        lines = output.strip().split('\n')
        
        # Extract headers
        headers = [
            col.strip() for col in lines[0].split('│')
            if col.strip()
        ]
        
        # Parse rows
        records = []
        for line in lines[2:]:  # Skip header and separator
            if '│' not in line:  # Skip separator lines
                continue
                
            values = [
                col.strip() for col in line.split('│')
                if col.strip()
            ]
            
            if len(values) == len(headers):
                record = dict(zip(headers, values))
                records.append(record)
                
        return records
        
    @staticmethod
    def _is_list(output: str) -> bool:
        """Check if output appears to be a list"""
        lines = output.strip().split('\n')
        return all(line.startswith(('- ', '* ')) for line in lines)
        
    @staticmethod
    def _parse_list(output: str) -> List[str]:
        """Parse Nu list output into Python list"""
        return [
            line[2:].strip()  # Remove list marker
            for line in output.strip().split('\n')
        ]
        
    @staticmethod
    def _infer_schema(data: List[Dict]) -> Dict:
        """Infer schema from parsed data"""
        if not data:
            return {}
            
        schema = {}
        sample = data[0]
        
        for key, value in sample.items():
            # Infer type
            if value.isdigit():
                schema[key] = 'number'
            elif value.lower() in ('true', 'false'):
                schema[key] = 'boolean'
            else:
                schema[key] = 'string'
                
        return schema

class ShellAdapter:
    """Enhanced shell adapter with structured output support"""
    
    def __init__(self, preferred_shell: str = 'nu', security_manager=None):
        self.preferred_shell = ShellType(preferred_shell)
        self.transpiler = ShellTranspiler(security_manager)
        self.command_history: List[Dict] = []
        self.working_dir = Path.cwd()
        self.nu_parser = NuOutputParser()
        self.security_manager = security_manager
        
    async def execute(self, command: str) -> Tuple[StructuredOutput, str, int]:
        """Execute command with structured output handling"""
        try:
            # Prepare command based on shell preference
            if self.preferred_shell == ShellType.NU:
                if not command.endswith('| to json'):
                    command += " | to json"
                    
            # Validate command
            warnings = self.transpiler._validate_command(command, self.preferred_shell)
            if warnings and self.security_manager:
                # Check security policies
                if not self.security_manager.check_command_capability(
                    command,
                    'basic_execution'
                ):
                    return StructuredOutput(
                        raw_output="",
                        data={"error": "Command blocked by security policy"},
                        format_type='error'
                    ), "\n".join(warnings), 1
                    
            # Execute command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir),
                env={'SHELL': f'/bin/{self.preferred_shell.value}'}
            )
            
            stdout, stderr = await process.communicate()
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""
            
            # Parse output
            if self.preferred_shell == ShellType.NU:
                output = self.nu_parser.parse_output(stdout_str)
            else:
                output = StructuredOutput(
                    raw_output=stdout_str,
                    data=stdout_str,
                    format_type='plain'
                )
                
            # Store command history
            self.command_history.append({
                'command': command,
                'shell': self.preferred_shell.value,
                'output': output.to_json(),
                'warnings': warnings,
                'code': process.returncode
            })
            
            return output, stderr_str, process.returncode
            
        except Exception as e:
            error_msg = f"Error executing command: {str(e)}"
            logger.error(error_msg)
            return StructuredOutput(
                raw_output="",
                data={"error": error_msg},
                format_type='error'
            ), error_msg, 1
    
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