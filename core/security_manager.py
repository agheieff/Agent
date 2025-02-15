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
    
    # Shell-specific dangerous patterns
    SHELL_PATTERNS = {
        'bash': {
            'SYSTEM_WIPE': [
                r'rm\s+-rf\s+[/~]',
                r'shred\s+-u\s+[/~]'
            ],
            'PERMISSION_CHANGE': [
                r'chmod\s+777',
                r'chmod\s+-R\s+777'
            ],
            'NETWORK_EXPOSURE': [
                r'nc\s+-l',
                r'netcat\s+-l',
                r'python\s+-m\s+http\.server'
            ]
        },
        'nu': {
            'SYSTEM_WIPE': [
                r'rm\s+-rf\s+[/~]',
                r'remove-item\s+-r\s+[/~]'
            ],
            'PERMISSION_CHANGE': [
                r'chmod\s+777',
                r'set\s+mode\s+777'
            ],
            'NETWORK_EXPOSURE': [
                r'listen\s+tcp',
                r'serve\s+http'
            ]
        }
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
            
    def validate_command(self, command: str, shell_type: str) -> Dict:
        """Validate command against security rules with shell-specific checks"""
        results = {
            'is_safe': True,
            'warnings': [],
            'blocked_patterns': [],
            'required_capabilities': set(),
            'resource_requirements': {}
        }
        
        # Get shell-specific patterns
        patterns = self.SHELL_PATTERNS.get(shell_type, {})
        
        # Check for dangerous patterns
        for danger_type, danger_patterns in patterns.items():
            for pattern in danger_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    results['is_safe'] = False
                    results['blocked_patterns'].append(
                        f"{danger_type}: {pattern}"
                    )
        
        # Estimate resource requirements
        results['resource_requirements'] = self._estimate_resources(command)
        
        # Determine required capabilities
        results['required_capabilities'] = self._determine_capabilities(
            command,
            shell_type
        )
        
        return results
        
    def _estimate_resources(self, command: str) -> Dict:
        """Estimate resource requirements for command"""
        resources = {
            'cpu': 'low',
            'memory': 'low',
            'disk': 'low',
            'network': 'none'
        }
        
        # CPU intensive operations
        cpu_patterns = [
            r'find',
            r'grep\s+-r',
            r'sort',
            r'where\s+.*\|\s+sort-by',
            r'compress',
            r'tar',
            r'zip'
        ]
        if any(re.search(p, command) for p in cpu_patterns):
            resources['cpu'] = 'medium'
            
        # Memory intensive operations
        memory_patterns = [
            r'sort\s+-S',
            r'convert',
            r'ffmpeg',
            r'where\s+.*\|\s+group-by'
        ]
        if any(re.search(p, command) for p in memory_patterns):
            resources['memory'] = 'high'
            
        # Disk intensive operations
        disk_patterns = [
            r'dd',
            r'rsync',
            r'cp\s+-r',
            r'mv\s+.*\s+/',
            r'save\s+.*\s+/'
        ]
        if any(re.search(p, command) for p in disk_patterns):
            resources['disk'] = 'high'
            
        # Network operations
        network_patterns = [
            r'curl',
            r'wget',
            r'fetch',
            r'ssh',
            r'scp',
            r'rsync\s+.*:',
            r'git\s+clone'
        ]
        if any(re.search(p, command) for p in network_patterns):
            resources['network'] = 'active'
            
        return resources
        
    def _determine_capabilities(self, command: str, shell_type: str) -> Set[str]:
        """Determine required capabilities for command"""
        capabilities = set()
        
        # Basic execution always required
        capabilities.add('basic_execution')
        
        # Shell-specific capability checks
        if shell_type == 'nu':
            if any(p in command for p in ['save', 'append', 'open']):
                capabilities.add('file_operations')
            if 'http' in command or 'fetch' in command:
                capabilities.add('network_operations')
        else:  # bash
            if any(p in command for p in ['>', '>>', 'cat', 'cp', 'mv']):
                capabilities.add('file_operations')
            if any(p in command for p in ['curl', 'wget', 'nc']):
                capabilities.add('network_operations')
                
        # Common capability checks
        if 'sudo' in command or 'doas' in command:
            capabilities.add('privileged_execution')
        if any(p in command for p in ['systemctl', 'service']):
            capabilities.add('service_management')
            
        return capabilities
        
    def apply_resource_limits(self, requirements: Dict):
        """Apply resource limits based on requirements"""
        try:
            # CPU limits
            if requirements['cpu'] == 'low':
                cpu_limit = 30  # 30 seconds
            elif requirements['cpu'] == 'medium':
                cpu_limit = 300  # 5 minutes
            else:
                cpu_limit = 3600  # 1 hour
                
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_limit))
            
            # Memory limits
            if requirements['memory'] == 'low':
                mem_limit = 512 * 1024 * 1024  # 512MB
            elif requirements['memory'] == 'medium':
                mem_limit = 2 * 1024 * 1024 * 1024  # 2GB
            else:
                mem_limit = 8 * 1024 * 1024 * 1024  # 8GB
                
            resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
            
            # Process limits based on CPU intensity
            if requirements['cpu'] == 'low':
                proc_limit = 50
            else:
                proc_limit = 200
                
            resource.setrlimit(resource.RLIMIT_NPROC, (proc_limit, proc_limit))
            
            # File size limits based on disk usage
            if requirements['disk'] == 'low':
                file_limit = 100 * 1024 * 1024  # 100MB
            elif requirements['disk'] == 'medium':
                file_limit = 1024 * 1024 * 1024  # 1GB
            else:
                file_limit = 10 * 1024 * 1024 * 1024  # 10GB
                
            resource.setrlimit(resource.RLIMIT_FSIZE, (file_limit, file_limit))
            
        except Exception as e:
            logger.error(f"Error applying resource limits: {e}")
            
    def track_resource_usage(self, pid: int) -> Dict:
        """Track resource usage of a process"""
        try:
            with open(f"/proc/{pid}/status") as f:
                status = f.read()
                
            with open(f"/proc/{pid}/stat") as f:
                stat = f.read().split()
                
            # Extract memory usage
            vm_peak = re.search(r'VmPeak:\s+(\d+)', status)
            vm_peak = int(vm_peak.group(1)) if vm_peak else 0
            
            # Extract CPU usage
            utime = int(stat[13])
            stime = int(stat[14])
            
            return {
                'memory_peak_kb': vm_peak,
                'cpu_user_time': utime,
                'cpu_system_time': stime,
                'total_cpu_time': utime + stime
            }
            
        except Exception as e:
            logger.error(f"Error tracking resource usage: {e}")
            return {}
        
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
            
    def create_restricted_environment(self, shell_type: str) -> Dict[str, str]:
        """Create a restricted environment for specific shell"""
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
            
        # Set safe PATH based on shell
        if shell_type == 'nu':
            env['PATH'] = '/usr/local/bin:/usr/bin:/bin'
        else:
            env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
            
        # Set appropriate shell
        env['SHELL'] = f'/bin/{shell_type}'
        
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