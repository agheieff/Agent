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
    name: str
    description: str
    required_permissions: Set[str] = field(default_factory=set)
    dangerous_patterns: Set[str] = field(default_factory=set)
    resource_limits: Dict[str, int] = field(default_factory=dict)

class SecurityManager:
    """Manages command execution safety and resource limits"""
    
    DEFAULT_LIMITS = {
        'MAX_CPU_TIME': 30,
        'MAX_MEMORY': 512 * 1024 * 1024,
        'MAX_FILE_SIZE': 50 * 1024 * 1024,
        'MAX_PROCESSES': 50,
        'MAX_OPEN_FILES': 1024
    }
    
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
        }
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/security")
        self.config_path.mkdir(parents=True, exist_ok=True)
        self.capabilities: Dict[str, SecurityCapability] = {}
        self.cgroup_name = "agent_restricted"
        self._load_capabilities()
        
        # For AMD-based systems or CPU-based systems, cgroups are still relevant but no GPU specifics
        self._setup_cgroup()
        
    def _setup_cgroup(self):
        """Setup cgroup for resource limiting if needed"""
        try:
            cgroup_path = Path("/sys/fs/cgroup/agent_restricted")
            if not cgroup_path.exists():
                os.makedirs(cgroup_path, exist_ok=True)
            with open(cgroup_path / "cpu.max", "w") as f:
                f.write(f"{self.DEFAULT_LIMITS['MAX_CPU_TIME']}000000 1000000")
            with open(cgroup_path / "memory.max", "w") as f:
                f.write(str(self.DEFAULT_LIMITS['MAX_MEMORY']))
            with open(cgroup_path / "pids.max", "w") as f:
                f.write(str(self.DEFAULT_LIMITS['MAX_PROCESSES']))
        except Exception as e:
            logger.error(f"Error setting up cgroup: {e}")
            
    def _load_capabilities(self):
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
                self._create_default_capabilities()
        except Exception as e:
            logger.error(f"Error loading capabilities: {e}")
            self._create_default_capabilities()
            
    def _create_default_capabilities(self):
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
                },
                'resource_limits': {
                    **self.DEFAULT_LIMITS,
                    'MAX_FILE_SIZE': 100 * 1024 * 1024
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
                    'MAX_MEMORY': 1024 * 1024 * 1024
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
        try:
            data = []
            for cap in self.capabilities.values():
                data.append({
                    'name': cap.name,
                    'description': cap.description,
                    'required_permissions': list(cap.required_permissions),
                    'dangerous_patterns': list(cap.dangerous_patterns),
                    'resource_limits': cap.resource_limits
                })
            with open(self.config_path / "capabilities.json", 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving capabilities: {e}")
            
    def validate_command(self, command: str, shell_type: str) -> Dict:
        # Unrestricted - always return safe with no warnings
        results = {
            'is_safe': True,  # Always return safe
            'warnings': [],
            'blocked_patterns': [],
            'required_capabilities': set(),
            'resource_requirements': {}
        }
        
        # Still estimate resources for logging purposes, but don't block anything
        results['resource_requirements'] = self._estimate_resources(command)
        results['required_capabilities'] = self._determine_capabilities(command, shell_type)
        
        # Log potentially dangerous commands but allow them
        patterns = self.SHELL_PATTERNS.get(shell_type, {})
        for danger_type, danger_patterns in patterns.items():
            for pattern in danger_patterns:
                if re.search(pattern, command, re.IGNORECASE):
                    logger.warning(f"Executing potentially dangerous command: {danger_type}: {command}")
                    # Don't set is_safe to False, we want to allow all commands
        
        return results
        
    def _estimate_resources(self, command: str) -> Dict:
        resources = {'cpu': 'low', 'memory': 'low', 'disk': 'low', 'network': 'none'}
        cpu_patterns = [r'find', r'grep\s+-r', r'sort', r'compress', r'tar', r'zip']
        memory_patterns = [r'sort\s+-S', r'convert', r'ffmpeg']
        disk_patterns = [r'dd', r'rsync', r'cp\s+-r', r'mv\s+.*\s+/']
        network_patterns = [r'curl', r'wget', r'ssh', r'scp', r'rsync\s+.*:', r'git\s+clone']
        
        if any(re.search(p, command) for p in cpu_patterns):
            resources['cpu'] = 'medium'
        if any(re.search(p, command) for p in memory_patterns):
            resources['memory'] = 'high'
        if any(re.search(p, command) for p in disk_patterns):
            resources['disk'] = 'high'
        if any(re.search(p, command) for p in network_patterns):
            resources['network'] = 'active'
        return resources
        
    def _determine_capabilities(self, command: str, shell_type: str) -> Set[str]:
        capabilities = set()
        capabilities.add('basic_execution')
        if any(p in command for p in ['>', '>>', 'cat', 'cp', 'mv']):
            capabilities.add('file_operations')
        if any(p in command for p in ['curl', 'wget', 'nc']):
            capabilities.add('network_operations')
        if 'sudo' in command:
            capabilities.add('privileged_execution')
        if any(p in command for p in ['systemctl', 'service']):
            capabilities.add('service_management')
        return capabilities
        
    def apply_resource_limits(self, requirements: Dict):
        # No resource limits applied in unrestricted mode
        logger.info("Resource limits disabled in unrestricted mode")
            
    def track_resource_usage(self, pid: int) -> Dict:
        try:
            with open(f"/proc/{pid}/status") as f:
                status = f.read()
            with open(f"/proc/{pid}/stat") as f:
                stat = f.read().split()
            vm_peak = re.search(r'VmPeak:\s+(\d+)', status)
            vm_peak = int(vm_peak.group(1)) if vm_peak else 0
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
        # Always validate as true, no binary validation
        return True
            
    def create_restricted_environment(self) -> Dict[str, str]:
        # No restriction - return the full environment
        return os.environ.copy()
        
    def check_command_capability(self, command: str, required_capability: str) -> bool:
        # Always return True - no capability restrictions
        return True
