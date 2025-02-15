import asyncio
import logging
from typing import Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass
from datetime import datetime
import networkx as nx
from pathlib import Path
import json

logger = logging.getLogger(__name__)

@dataclass
class CommandNode:
    """Represents a command in a sequence"""
    id: str
    command: str
    command_type: str
    dependencies: List[str]
    timeout: float
    retry_count: int
    required: bool
    description: str
    metadata: Dict = None
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'command': self.command,
            'command_type': self.command_type,
            'dependencies': self.dependencies,
            'timeout': self.timeout,
            'retry_count': self.retry_count,
            'required': self.required,
            'description': self.description,
            'metadata': self.metadata or {}
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'CommandNode':
        return CommandNode(**data)

class CommandSequence:
    """Manages a sequence of dependent commands"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.graph = nx.DiGraph()
        self.executed: Set[str] = set()
        self.failed: Set[str] = set()
        
    def add_command(self, command: CommandNode, dependencies: List[str] = None):
        """Add a command to the sequence with optional dependencies"""
        self.graph.add_node(command.id, command=command)
        if dependencies:
            for dep in dependencies:
                if dep in self.graph:
                    self.graph.add_edge(dep, command.id)
                    
    def get_ready_commands(self) -> List[CommandNode]:
        """Get commands whose dependencies have been satisfied"""
        ready = []
        for node in self.graph.nodes:
            if node not in self.executed and node not in self.failed:
                deps = list(self.graph.predecessors(node))
                if all(d in self.executed for d in deps):
                    ready.append(self.graph.nodes[node]['command'])
        return ready
    
    def mark_executed(self, command_id: str):
        """Mark a command as successfully executed"""
        self.executed.add(command_id)
        
    def mark_failed(self, command_id: str):
        """Mark a command as failed"""
        self.failed.add(command_id)
        
    def is_complete(self) -> bool:
        """Check if sequence is complete"""
        return all(node in self.executed or node in self.failed 
                  for node in self.graph.nodes)
    
    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'description': self.description,
            'nodes': [
                {
                    'id': node,
                    'command': self.graph.nodes[node]['command'].to_dict()
                }
                for node in self.graph.nodes
            ],
            'edges': [
                {'from': edge[0], 'to': edge[1]}
                for edge in self.graph.edges
            ],
            'executed': list(self.executed),
            'failed': list(self.failed)
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'CommandSequence':
        seq = CommandSequence(data['name'], data['description'])
        for node in data['nodes']:
            command = CommandNode.from_dict(node['command'])
            seq.graph.add_node(node['id'], command=command)
        for edge in data['edges']:
            seq.graph.add_edge(edge['from'], edge['to'])
        seq.executed = set(data['executed'])
        seq.failed = set(data['failed'])
        return seq

class CommandManager:
    """Manages command sequences and their execution"""
    
    def __init__(self, system_control, memory_manager, storage_path: Path = None):
        self.system_control = system_control
        self.memory_manager = memory_manager
        self.storage_path = storage_path or Path("memory/commands")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.active_sequences: Dict[str, CommandSequence] = {}
        self._load_sequences()
        
    def _load_sequences(self):
        """Load saved command sequences"""
        try:
            for file in self.storage_path.glob("*.json"):
                with open(file, 'r') as f:
                    data = json.load(f)
                    sequence = CommandSequence.from_dict(data)
                    self.active_sequences[sequence.name] = sequence
        except Exception as e:
            logger.error(f"Error loading sequences: {e}")
            
    def _save_sequences(self):
        """Save command sequences to disk"""
        try:
            for name, sequence in self.active_sequences.items():
                with open(self.storage_path / f"{name}.json", 'w') as f:
                    json.dump(sequence.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Error saving sequences: {e}")
            
    def create_sequence(self, name: str, description: str = "") -> CommandSequence:
        """Create a new command sequence"""
        sequence = CommandSequence(name, description)
        self.active_sequences[name] = sequence
        self._save_sequences()
        return sequence
        
    async def execute_sequence(self, sequence_name: str) -> bool:
        """Execute a command sequence"""
        sequence = self.active_sequences.get(sequence_name)
        if not sequence:
            logger.error(f"Sequence {sequence_name} not found")
            return False
            
        try:
            while not sequence.is_complete():
                ready_commands = sequence.get_ready_commands()
                if not ready_commands:
                    break
                    
                for command in ready_commands:
                    success = await self._execute_command(command)
                    if success:
                        sequence.mark_executed(command.id)
                    else:
                        sequence.mark_failed(command.id)
                        if command.required:
                            logger.error(f"Required command {command.id} failed")
                            return False
                            
                self._save_sequences()
                
            return all(node not in sequence.failed 
                      for node in sequence.graph.nodes 
                      if sequence.graph.nodes[node]['command'].required)
                      
        except Exception as e:
            logger.error(f"Error executing sequence {sequence_name}: {e}")
            return False
            
    async def _execute_command(self, command: CommandNode) -> bool:
        """Execute a single command with retries"""
        for attempt in range(command.retry_count + 1):
            try:
                stdout, stderr, code = await asyncio.wait_for(
                    self.system_control.execute_command(
                        command.command_type,
                        command.command
                    ),
                    timeout=command.timeout
                )
                
                # Save execution result to memory
                self.memory_manager.save_document(
                    f"command_execution_{command.id}_{datetime.now().isoformat()}",
                    f"Command: {command.command}\nType: {command.command_type}\n"
                    f"Attempt: {attempt + 1}\nResult:\n{stdout}\n{stderr}",
                    metadata={
                        'command_id': command.id,
                        'exit_code': code,
                        'attempt': attempt + 1
                    }
                )
                
                if code == 0:
                    return True
                    
                if attempt < command.retry_count:
                    logger.warning(f"Command {command.id} failed, retrying...")
                    await asyncio.sleep(1)  # Wait before retry
                    
            except asyncio.TimeoutError:
                logger.error(f"Command {command.id} timed out")
                break
            except Exception as e:
                logger.error(f"Error executing command {command.id}: {e}")
                break
                
        return False
        
    def get_sequence_status(self, sequence_name: str) -> Dict:
        """Get status of a command sequence"""
        sequence = self.active_sequences.get(sequence_name)
        if not sequence:
            return {}
            
        total = len(sequence.graph.nodes)
        executed = len(sequence.executed)
        failed = len(sequence.failed)
        
        return {
            'name': sequence.name,
            'description': sequence.description,
            'total_commands': total,
            'executed': executed,
            'failed': failed,
            'pending': total - executed - failed,
            'success_rate': executed / total if total > 0 else 0,
            'is_complete': sequence.is_complete(),
            'failed_required': any(
                node in sequence.failed and sequence.graph.nodes[node]['command'].required
                for node in sequence.graph.nodes
            )
        } 