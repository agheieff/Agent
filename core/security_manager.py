import logging
import os
import re
import json
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import resource
import pwd

logger = logging.getLogger(__name__)

@dataclass
class SecurityCapability:
    """Represents a security capability"""
    name: str
    description: str
    required_permissions: Set[str] = field(default_factory=set)
    dangerous_patterns: Set[str] = field(default_factory=set)
    resource_limits: Dict[str, int] = field(default_factory=dict)

class SecurityManager:
    """Manages command execution safety and resource limits"""
    
    # Default resource limits
    DEFAULT_LIMITS = {
        'MAX_CPU_TIME': 30,  # seconds
        'MAX_MEMORY': 512 * 1024 * 1024,  # 512MB
        'MAX_FILE_SIZE': 50 * 1024 * 1024,  # 50MB
        'MAX_PROCESSES': 50,
        'MAX_OPEN_FILES': 1024
    }
    
    # Dangerous patterns for both Bash and Nu shell
    DANGEROUS_PATTERNS = {
        'SYSTEM_WIPE': [
            r'rm\s+-rf\s+[/~]',
            r'remove-item\s+-Recurse\s+-Force\s+[/~]'
        ],
        'PERMISSION_CHANGE': [
            r'chmod\s+777',
            r'chmod\s+-R\s+777',
            r'icacls\s+.*\s+\/grant\s+Everyone:F'
        ],
        'NETWORK_EXPOSURE': [
            r'nc\s+-l',
            r'netcat\s+-l',
            r'python\s+-m\s+http\.server'
        ],
        'DANGEROUS_DOWNLOAD': [
            r'curl\s+.*\s+\|\s+bash',
            r'wget\s+.*\s+\|\s+bash',
            r'iwr\s+.*\s+\|\s+iex'
        ]
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/security")
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.capabilities: Dict[str, SecurityCapability] = {}
        self.cgroup_name = "agent_restricted"
        self._setup_cgroup()
        self._load_capabilities()
        
    def _setup_cgroup(self):
        """Setup cgroup for resource limiting"""
        try:
            # Create cgroup
            cgroup_path = Path("/sys/fs/cgroup/agent_restricted")
            if not cgroup_path.exists():
                os.makedirs(cgroup_path, exist_ok=True)
                
            # Set default resource limits
            with open(cgroup_path / "cpu.max", "w") as f:
                f.write(f"{self.DEFAULT_LIMITS['MAX_CPU_TIME']}000000 1000000")
            with open(cgroup_path / "memory.max", "w") as f:
                f.write(str(self.DEFAULT_LIMITS['MAX_MEMORY']))
            with open(cgroup_path / "pids.max", "w") as f:
                f.write(str(self.DEFAULT_LIMITS['MAX_PROCESSES']))
                
        except Exception as e:
            logger.error(f"Error setting up cgroup: {e}")
            
    def _load_capabilities(self):
        """Load security capabilities from config"""
        try:
            cap_file = self.config_path / "capabilities.json"
            if cap_file.exists():
                with open(cap_file, 'r') as f:
                    data = json.load(f)
                    for cap_data in data:
                        self.capabilities[cap_data['name']] = SecurityCapability(
                            name=cap_data['name'],
                            description=cap_data['description'],
                            required_permissions=set(cap_data['required_permissions']),
                            dangerous_patterns=set(cap_data['dangerous_patterns']),
                            resource_limits=cap_data['resource_limits']
                        )
            else:
                # Create default capabilities
                self._create_default_capabilities()
                
        except Exception as e:
            logger.error(f"Error loading capabilities: {e}")
            self._create_default_capabilities()
            
    def _create_default_capabilities(self):
        """Create default security capabilities"""
        defaults = {
            'basic_execution': {
                'description': 'Basic command execution with minimal privileges',
                'required_permissions': {'execute'},
                'dangerous_patterns': set(),
                'resource_limits': self.DEFAULT_LIMITS.copy()
            },
            'file_operations': {
                'description': 'File read/write operations',
                'required_permissions': {'execute', 'file_read', 'file_write'},
                'dangerous_patterns': {
                    r'rm\s+-rf',
                    r'remove-item\s+-Recurse\s+-Force'
                },
                'resource_limits': {
                    **self.DEFAULT_LIMITS,
                    'MAX_FILE_SIZE': 100 * 1024 * 1024  # 100MB
                }
            },
            'network_operations': {
                'description': 'Network-related operations',
                'required_permissions': {'execute', 'network'},
                'dangerous_patterns': {
                    r'nc\s+-l',
                    r'netcat\s+-l'
                },
                'resource_limits': {
                    **self.DEFAULT_LIMITS,
                    'MAX_MEMORY': 1024 * 1024 * 1024  # 1GB
                }
            }
        }
        
        for name, data in defaults.items():
            self.capabilities[name] = SecurityCapability(
                name=name,
                **data
            )
            
        self._save_capabilities()
        
    def _save_capabilities(self):
        """Save security capabilities to config"""
        try:
            data = [
                {
                    'name': cap.name,
                    'description': cap.description,
                    'required_permissions': list(cap.required_permissions),
                    'dangerous_patterns': list(cap.dangerous_patterns),
                    'resource_limits': cap.resource_limits
                }
                for cap in self.capabilities.values()
            ]
            
            with open(self.config_path / "capabilities.json", 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving capabilities: {e}")
            
    def validate_command(self, command: str, shell_type: str = 'bash') -> Dict:
        """Validate command against security rules"""
        results = {
            'is_safe': True,
            'warnings': [],
            'blocked_patterns': [],
            'required_capabilities': set()
        }
        
        # Check for dangerous patterns
        for danger_type, patterns in self.DANGEROUS_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    results['is_safe'] = False
                    results['blocked_patterns'].append(
                        f"{danger_type}: {pattern}"
                    )
                    
        # Check shell-specific patterns
        if shell_type == 'nu':
            # Add Nu shell specific checks
            nu_patterns = [
                (r'rm\s+-rf\s+/', "Dangerous system deletion"),
                (r'sudo\s+rm', "Privileged deletion"),
                (r'open\s+.*\s+\|\s+save', "Unsafe file redirection")
            ]
            for pattern, warning in nu_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    results['warnings'].append(warning)
                    
        # Determine required capabilities
        if 'sudo' in command or 'doas' in command:
            results['required_capabilities'].add('privileged_execution')
        if any(pat in command for pat in ['cp', 'mv', 'rm', 'touch']):
            results['required_capabilities'].add('file_operations')
        if any(pat in command for pat in ['curl', 'wget', 'nc', 'ssh']):
            results['required_capabilities'].add('network_operations')
            
        return results
        
    def apply_resource_limits(self):
        """Apply resource limits using cgroups and rlimit"""
        try:
            # Set process resource limits
            resource.setrlimit(resource.RLIMIT_CPU, 
                             (self.DEFAULT_LIMITS['MAX_CPU_TIME'], 
                              self.DEFAULT_LIMITS['MAX_CPU_TIME']))
            resource.setrlimit(resource.RLIMIT_AS, 
                             (self.DEFAULT_LIMITS['MAX_MEMORY'],
                              self.DEFAULT_LIMITS['MAX_MEMORY']))
            resource.setrlimit(resource.RLIMIT_FSIZE,
                             (self.DEFAULT_LIMITS['MAX_FILE_SIZE'],
                              self.DEFAULT_LIMITS['MAX_FILE_SIZE']))
            resource.setrlimit(resource.RLIMIT_NOFILE,
                             (self.DEFAULT_LIMITS['MAX_OPEN_FILES'],
                              self.DEFAULT_LIMITS['MAX_OPEN_FILES']))
            
            # Add process to cgroup
            pid = os.getpid()
            cgroup_path = Path(f"/sys/fs/cgroup/{self.cgroup_name}/cgroup.procs")
            if cgroup_path.exists():
                with open(cgroup_path, "a") as f:
                    f.write(str(pid))
                    
        except Exception as e:
            logger.error(f"Error applying resource limits: {e}")
            
    def validate_binary(self, command: str) -> bool:
        """Validate binary existence and permissions"""
        try:
            cmd_parts = command.split()
            if not cmd_parts:
                return False
                
            binary = cmd_parts[0]
            result = subprocess.run(
                ['command', '-v', binary],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return False
                
            # Check binary permissions
            binary_path = result.stdout.strip()
            stats = os.stat(binary_path)
            
            # Ensure binary is not world-writable
            if stats.st_mode & 0o002:
                return False
                
            # Ensure binary is owned by root or current user
            current_user = pwd.getpwuid(os.getuid()).pw_name
            binary_owner = pwd.getpwuid(stats.st_uid).pw_name
            if binary_owner not in ['root', current_user]:
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error validating binary: {e}")
            return False
            
    def create_restricted_environment(self) -> Dict[str, str]:
        """Create a restricted environment for command execution"""
        env = os.environ.copy()
        
        # Remove potentially dangerous environment variables
        dangerous_vars = {
            'LD_PRELOAD',
            'LD_LIBRARY_PATH',
            'PYTHONPATH',
            'PATH',
            'SHELL'
        }
        
        for var in dangerous_vars:
            env.pop(var, None)
            
        # Set safe PATH
        env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
        
        # Set safe shell
        env['SHELL'] = '/bin/bash'
        
        return env
        
    def check_command_capability(self, command: str,
                               required_capability: str) -> bool:
        """Check if command has required capability"""
        if required_capability not in self.capabilities:
            return False
            
        capability = self.capabilities[required_capability]
        
        # Check for dangerous patterns
        for pattern in capability.dangerous_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False
                
        return True 