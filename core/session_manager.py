import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import time
import numpy as np
from collections import Counter

logger = logging.getLogger(__name__)

@dataclass
class CommandSkill:
    """Represents a learned command skill"""
    command_pattern: str
    description: str
    examples: List[str]
    success_count: int = 0
    fail_count: int = 0
    last_used: float = field(default_factory=time.time)
    contexts: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict:
        return {
            'command_pattern': self.command_pattern,
            'description': self.description,
            'examples': self.examples,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'last_used': self.last_used,
            'contexts': list(self.contexts)
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'CommandSkill':
        return CommandSkill(
            command_pattern=data['command_pattern'],
            description=data['description'],
            examples=data['examples'],
            success_count=data['success_count'],
            fail_count=data['fail_count'],
            last_used=data['last_used'],
            contexts=set(data['contexts'])
        )

@dataclass
class SessionState:
    """Represents the state of a session"""
    id: str
    start_time: float
    shell_preference: str
    working_directory: str
    environment: Dict[str, str]
    command_history: List[Dict]
    active_contexts: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'start_time': self.start_time,
            'shell_preference': self.shell_preference,
            'working_directory': self.working_directory,
            'environment': self.environment,
            'command_history': self.command_history,
            'active_contexts': list(self.active_contexts),
            'metadata': self.metadata
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'SessionState':
        return SessionState(
            id=data['id'],
            start_time=data['start_time'],
            shell_preference=data['shell_preference'],
            working_directory=data['working_directory'],
            environment=data['environment'],
            command_history=data['command_history'],
            active_contexts=set(data['active_contexts']),
            metadata=data['metadata']
        )

class SessionManager:
    """Manages session continuity and command learning"""
    
    def __init__(self, storage_path: Path, memory_manager=None):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.memory_manager = memory_manager
        
        self.current_session: Optional[SessionState] = None
        self.command_skills: Dict[str, CommandSkill] = {}
        self.context_transitions: Dict[str, Counter] = {}
        
        self._load_state()
        
    def _load_state(self):
        """Load session state and learned skills"""
        try:
            # Load last session
            session_file = self.storage_path / "last_session.json"
            if session_file.exists():
                with open(session_file, 'r') as f:
                    self.current_session = SessionState.from_dict(json.load(f))
                    
            # Load command skills
            skills_file = self.storage_path / "command_skills.json"
            if skills_file.exists():
                with open(skills_file, 'r') as f:
                    skills_data = json.load(f)
                    self.command_skills = {
                        pattern: CommandSkill.from_dict(data)
                        for pattern, data in skills_data.items()
                    }
                    
            # Load context transitions
            transitions_file = self.storage_path / "context_transitions.json"
            if transitions_file.exists():
                with open(transitions_file, 'r') as f:
                    transitions = json.load(f)
                    self.context_transitions = {
                        ctx: Counter(trans)
                        for ctx, trans in transitions.items()
                    }
                    
        except Exception as e:
            logger.error(f"Error loading session state: {e}")
            
    def _save_state(self):
        """Save session state and learned skills"""
        try:
            # Save current session
            if self.current_session:
                with open(self.storage_path / "last_session.json", 'w') as f:
                    json.dump(self.current_session.to_dict(), f, indent=2)
                    
            # Save command skills
            with open(self.storage_path / "command_skills.json", 'w') as f:
                json.dump(
                    {
                        pattern: skill.to_dict()
                        for pattern, skill in self.command_skills.items()
                    },
                    f,
                    indent=2
                )
                
            # Save context transitions
            with open(self.storage_path / "context_transitions.json", 'w') as f:
                json.dump(
                    {
                        ctx: dict(trans)
                        for ctx, trans in self.context_transitions.items()
                    },
                    f,
                    indent=2
                )
                
        except Exception as e:
            logger.error(f"Error saving session state: {e}")
            
    def start_session(self, shell_preference: str, working_directory: str,
                     environment: Dict[str, str]) -> SessionState:
        """Start a new session"""
        session = SessionState(
            id=f"session_{int(time.time())}",
            start_time=time.time(),
            shell_preference=shell_preference,
            working_directory=working_directory,
            environment=environment,
            command_history=[]
        )
        
        self.current_session = session
        self._save_state()
        return session
        
    def update_session(self, **updates) -> bool:
        """Update current session state"""
        if not self.current_session:
            return False
            
        for key, value in updates.items():
            if hasattr(self.current_session, key):
                setattr(self.current_session, key, value)
                
        self._save_state()
        return True
        
    def add_command(self, command: str, shell_type: str,
                    success: bool, context: Optional[str] = None):
        """Add command to history and update skills"""
        if not self.current_session:
            return
            
        # Add to session history
        self.current_session.command_history.append({
            'command': command,
            'shell_type': shell_type,
            'success': success,
            'timestamp': time.time(),
            'context': context
        })
        
        # Update context transitions
        if context:
            self.current_session.active_contexts.add(context)
            if len(self.current_session.command_history) > 1:
                prev_cmd = self.current_session.command_history[-2]
                prev_context = prev_cmd.get('context')
                if prev_context:
                    if prev_context not in self.context_transitions:
                        self.context_transitions[prev_context] = Counter()
                    self.context_transitions[prev_context][context] += 1
        
        # Learn command pattern
        pattern = self._extract_command_pattern(command)
        if pattern:
            if pattern not in self.command_skills:
                self.command_skills[pattern] = CommandSkill(
                    command_pattern=pattern,
                    description=self._generate_description(command),
                    examples=[command]
                )
            
            skill = self.command_skills[pattern]
            if success:
                skill.success_count += 1
            else:
                skill.fail_count += 1
            skill.last_used = time.time()
            if context:
                skill.contexts.add(context)
            if command not in skill.examples:
                skill.examples.append(command)
                
        self._save_state()
        
    def get_command_suggestions(self, context: Optional[str] = None,
                              k: int = 5) -> List[Dict]:
        """Get command suggestions based on context and history"""
        if not self.current_session:
            return []
            
        suggestions = []
        
        # Get suggestions from command skills
        for pattern, skill in self.command_skills.items():
            # Calculate base score from success rate
            total = skill.success_count + skill.fail_count
            if total == 0:
                continue
                
            score = skill.success_count / total
            
            # Boost score based on recency
            time_factor = 1.0 / (1.0 + (time.time() - skill.last_used))
            score *= (1 + time_factor)
            
            # Boost score if matching context
            if context and context in skill.contexts:
                score *= 1.5
                
            suggestions.append({
                'pattern': pattern,
                'description': skill.description,
                'examples': skill.examples[:3],
                'score': score
            })
            
        # Sort by score and return top k
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        return suggestions[:k]
        
    def predict_next_context(self) -> Optional[str]:
        """Predict next likely context based on transitions"""
        if not self.current_session or not self.current_session.active_contexts:
            return None
            
        current_context = list(self.current_session.active_contexts)[-1]
        if current_context not in self.context_transitions:
            return None
            
        transitions = self.context_transitions[current_context]
        if not transitions:
            return None
            
        return transitions.most_common(1)[0][0]
        
    def _extract_command_pattern(self, command: str) -> Optional[str]:
        """Extract general pattern from command"""
        try:
            parts = command.split()
            if not parts:
                return None
                
            # Keep first token (command) as is
            pattern = [parts[0]]
            
            # Replace arguments with placeholders
            for part in parts[1:]:
                if part.startswith('-'):
                    pattern.append(part)  # Keep flags as is
                elif part.startswith('/'):
                    pattern.append('<path>')
                elif part.isnumeric():
                    pattern.append('<number>')
                else:
                    pattern.append('<arg>')
                    
            return ' '.join(pattern)
            
        except Exception as e:
            logger.error(f"Error extracting command pattern: {e}")
            return None
            
    def _generate_description(self, command: str) -> str:
        """Generate description for command pattern"""
        try:
            if self.memory_manager:
                # Try to find similar commands in memory
                similar = self.memory_manager.search_memory(
                    command,
                    limit=1
                )
                if similar:
                    return similar[0]['content']
                    
            # Fallback to basic description
            parts = command.split()
            if not parts:
                return ""
                
            return f"Command using {parts[0]}"
            
        except Exception as e:
            logger.error(f"Error generating command description: {e}")
            return ""
            
    def get_session_stats(self) -> Dict[str, Any]:
        """Get statistics for current session"""
        if not self.current_session:
            return {}
            
        total_commands = len(self.current_session.command_history)
        if total_commands == 0:
            return {
                'duration': time.time() - self.current_session.start_time,
                'total_commands': 0
            }
            
        successful = sum(
            1 for cmd in self.current_session.command_history
            if cmd['success']
        )
        
        return {
            'duration': time.time() - self.current_session.start_time,
            'total_commands': total_commands,
            'success_rate': successful / total_commands,
            'shell_usage': Counter(
                cmd['shell_type']
                for cmd in self.current_session.command_history
            ),
            'contexts': list(self.current_session.active_contexts),
            'most_used_commands': Counter(
                cmd['command'].split()[0]
                for cmd in self.current_session.command_history
            ).most_common(5)
        } 