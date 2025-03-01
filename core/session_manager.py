import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
import time
import json
from pathlib import Path
import networkx as nx
from collections import Counter

logger = logging.getLogger(__name__)

@dataclass
class CommandSkill:
    command_pattern: str
    description: str
    examples: List[str]
    success_count: int = 0
    fail_count: int = 0
    last_used: float = field(default_factory=time.time)
    contexts: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(data: Dict[str, Any]) -> 'CommandSkill':
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
class SessionBranch:
    id: str
    parent_id: Optional[str]
    name: str
    description: str
    created_at: float
    command_history: List[Dict] = field(default_factory=list)
    context_inheritance: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'parent_id': self.parent_id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at,
            'command_history': self.command_history,
            'context_inheritance': self.context_inheritance,
            'metadata': self.metadata
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'SessionBranch':
        return SessionBranch(**data)

@dataclass
class SessionState:
    id: str
    start_time: float
    shell_preference: str
    working_directory: str
    environment: Dict[str, str]
    command_history: List[Dict]
    active_contexts: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    active_branch_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'start_time': self.start_time,
            'shell_preference': self.shell_preference,
            'working_directory': self.working_directory,
            'environment': self.environment,
            'command_history': self.command_history,
            'active_contexts': list(self.active_contexts),
            'metadata': self.metadata,
            'active_branch_id': self.active_branch_id
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'SessionState':
        data['active_contexts'] = set(data['active_contexts'])
        return SessionState(**data)

class SessionManager:
    """Manages session continuity, branching, and command learning"""
    
    def __init__(self, storage_path: Path, memory_manager=None):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.memory_manager = memory_manager
        
        self.current_session: Optional[SessionState] = None
        self.command_skills: Dict[str, CommandSkill] = {}
        self.context_transitions: Dict[str, Counter] = {}
        self.session_tree = nx.DiGraph()
        
        self._load_state()
        
    def _load_state(self):
        try:
            session_file = self.storage_path / "last_session.json"
            if session_file.exists():
                with open(session_file, 'r') as f:
                    self.current_session = SessionState.from_dict(json.load(f))
            tree_file = self.storage_path / "session_tree.json"
            if tree_file.exists():
                with open(tree_file, 'r') as f:
                    data = json.load(f)
                for branch_data in data['branches']:
                    branch = SessionBranch.from_dict(branch_data)
                    self.session_tree.add_node(branch.id, branch=branch)
                    if branch.parent_id:
                        self.session_tree.add_edge(branch.parent_id, branch.id)
            skills_file = self.storage_path / "command_skills.json"
            if skills_file.exists():
                with open(skills_file, 'r') as f:
                    skills_data = json.load(f)
                self.command_skills = {
                    pattern: CommandSkill.from_dict(sd)
                    for pattern, sd in skills_data.items()
                }
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
        try:
            if self.current_session:
                with open(self.storage_path / "last_session.json", 'w') as f:
                    json.dump(self.current_session.to_dict(), f, indent=2)
            with open(self.storage_path / "session_tree.json", 'w') as f:
                json.dump({
                    'branches': [
                        self.session_tree.nodes[node]['branch'].to_dict()
                        for node in self.session_tree.nodes
                    ]
                }, f, indent=2)
            with open(self.storage_path / "command_skills.json", 'w') as f:
                json.dump({
                    pattern: skill.to_dict()
                    for pattern, skill in self.command_skills.items()
                }, f, indent=2)
            with open(self.storage_path / "context_transitions.json", 'w') as f:
                json.dump({
                    ctx: dict(trans)
                    for ctx, trans in self.context_transitions.items()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving session state: {e}")
            
    def start_session(self, shell_preference: str, working_directory: str,
                      environment: Dict[str, str], session_id: str = None) -> SessionState:
        """Start a new session with the given parameters"""
        session = SessionState(
            id=session_id or f"session_{int(time.time())}",
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
        if not self.current_session:
            return False
        for k, v in updates.items():
            if hasattr(self.current_session, k):
                setattr(self.current_session, k, v)
        self._save_state()
        return True
        
    def add_command(self, command: str, shell_type: str, success: bool, context: Optional[str] = None):
        if not self.current_session:
            return
        self.current_session.command_history.append({
            'command': command,
            'shell_type': shell_type,
            'success': success,
            'timestamp': time.time(),
            'context': context
        })
        if context:
            self.current_session.active_contexts.add(context)
            if len(self.current_session.command_history) > 1:
                prev_cmd = self.current_session.command_history[-2]
                prev_context = prev_cmd.get('context')
                if prev_context:
                    if prev_context not in self.context_transitions:
                        self.context_transitions[prev_context] = Counter()
                    self.context_transitions[prev_context][context] += 1
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
        
    def get_command_suggestions(self, context: Optional[str] = None, k: int = 5) -> List[Dict]:
        suggestions = []
        for pattern, skill in self.command_skills.items():
            total = skill.success_count + skill.fail_count
            if total == 0:
                continue
            score = skill.success_count / total
            time_factor = 1.0 / (1.0 + (time.time() - skill.last_used))
            score *= (1 + time_factor)
            if context and context in skill.contexts:
                score *= 1.5
            suggestions.append({
                'pattern': pattern,
                'description': skill.description,
                'examples': skill.examples[:3],
                'score': score
            })
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        return suggestions[:k]
        
    def predict_next_context(self) -> Optional[str]:
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
        try:
            parts = command.split()
            if not parts:
                return None
            pattern = [parts[0]]
            for part in parts[1:]:
                if part.startswith('-'):
                    pattern.append(part)
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
        try:
            if self.memory_manager:
                similar = self.memory_manager.search_memory(command, limit=1)
                if similar:
                    return similar[0]['content']
            parts = command.split()
            if not parts:
                return ""
            return f"Command using {parts[0]}"
        except Exception as e:
            logger.error(f"Error generating command description: {e}")
            return ""
            
    def get_session_stats(self) -> Dict[str, Any]:
        if not self.current_session:
            return {}
        total_commands = len(self.current_session.command_history)
        if total_commands == 0:
            return {
                'duration': time.time() - self.current_session.start_time,
                'total_commands': 0
            }
        successful = sum(1 for c in self.current_session.command_history if c['success'])
        return {
            'duration': time.time() - self.current_session.start_time,
            'total_commands': total_commands,
            'success_rate': successful / total_commands,
            'shell_usage': Counter(c['shell_type'] for c in self.current_session.command_history),
            'contexts': list(self.current_session.active_contexts),
            'most_used_commands': Counter(c['command'].split()[0] for c in self.current_session.command_history).most_common(5)
        }
        
    def create_branch(self, name: str, description: str,
                     parent_id: Optional[str] = None,
                     inherit_context: bool = True) -> Optional[str]:
        try:
            branch_id = f"branch_{int(time.time())}"
            if not parent_id and self.current_session:
                parent_id = self.current_session.active_branch_id
            branch = SessionBranch(
                id=branch_id,
                parent_id=parent_id,
                name=name,
                description=description,
                created_at=time.time()
            )
            if inherit_context and parent_id:
                parent = self.get_branch(parent_id)
                if parent:
                    branch.context_inheritance = parent.context_inheritance.copy()
                    branch.command_history = parent.command_history[-5:]
            self.session_tree.add_node(branch_id, branch=branch)
            if parent_id:
                self.session_tree.add_edge(parent_id, branch_id)
            if self.current_session:
                self.current_session.active_branch_id = branch_id
            self._save_state()
            return branch_id
        except Exception as e:
            logger.error(f"Error creating branch: {e}")
            return None
            
    def get_branch(self, branch_id: str) -> Optional[SessionBranch]:
        if branch_id in self.session_tree:
            return self.session_tree.nodes[branch_id]['branch']
        return None
        
    def get_branch_path(self, branch_id: str) -> List[SessionBranch]:
        if branch_id not in self.session_tree:
            return []
        path = []
        current = branch_id
        while current is not None:
            branch = self.get_branch(current)
            if not branch:
                break
            path.append(branch)
            current = branch.parent_id
        return list(reversed(path))
        
    def switch_branch(self, branch_id: str) -> bool:
        if not self.current_session or branch_id not in self.session_tree:
            return False
        try:
            self.current_session.active_branch_id = branch_id
            branch = self.get_branch(branch_id)
            if branch:
                self.current_session.active_contexts.update(branch.context_inheritance)
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"Error switching branch: {e}")
            return False
            
    def get_branch_context(self, branch_id: str) -> Dict[str, Any]:
        try:
            context = {}
            path = self.get_branch_path(branch_id)
            for branch in path:
                if branch.command_history:
                    if 'commands' not in context:
                        context['commands'] = []
                    context['commands'].extend(branch.command_history)
                for ctx in branch.context_inheritance:
                    if ctx not in context:
                        context[ctx] = []
                    if self.memory_manager:
                        results = self.memory_manager.search_memory(ctx, limit=3)
                        context[ctx].extend(results)
            return context
        except Exception as e:
            logger.error(f"Error getting branch context: {e}")
            return {}
            
    def add_command_to_branch(self, branch_id: str, command: str,
                              shell_type: str, success: bool = True):
        try:
            branch = self.get_branch(branch_id)
            if not branch:
                return
            branch.command_history.append({
                'command': command,
                'shell_type': shell_type,
                'success': success,
                'timestamp': time.time()
            })
            self.add_command(command, shell_type, success)
            self._save_state()
        except Exception as e:
            logger.error(f"Error adding command to branch: {e}")
            
    def merge_branches(self, source_id: str, target_id: str) -> bool:
        try:
            source = self.get_branch(source_id)
            target = self.get_branch(target_id)
            if not source or not target:
                return False
            target.command_history.extend(source.command_history)
            for ctx in source.context_inheritance:
                if ctx not in target.context_inheritance:
                    target.context_inheritance.append(ctx)
            for _, child in self.session_tree.out_edges(source_id):
                self.session_tree.remove_edge(source_id, child)
                self.session_tree.add_edge(target_id, child)
                child_branch = self.get_branch(child)
                if child_branch:
                    child_branch.parent_id = target_id
            self.session_tree.remove_node(source_id)
            self._save_state()
            return True
        except Exception as e:
            logger.error(f"Error merging branches: {e}")
            return False
