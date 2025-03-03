"""
Type definitions for the Atom of Thoughts (AoT) module.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
import networkx as nx

class AtomStatus(Enum):
    """Status of atom execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

class AtomType(Enum):
    """Types of thought atoms"""
    RESEARCH = "research"       # Information gathering, lookup
    ANALYSIS = "analysis"       # Breaking down, examining, evaluating
    SYNTHESIS = "synthesis"     # Combining information, creating
    VERIFICATION = "verification"  # Testing, validating
    PLANNING = "planning"       # Outlining steps

@dataclass
class Atom:
    """A single unit of thought processing"""
    id: str
    type: AtomType
    description: str
    inputs: List[str]  # IDs of atoms this one depends on
    query: str         # The specific question or task for this atom
    
    # Optional fields
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class AtomResult:
    """Result of executing an atom"""
    atom_id: str
    status: AtomStatus
    content: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
class AtomDAG:
    """Directed Acyclic Graph representing atom dependencies"""
    def __init__(self, graph: nx.DiGraph, atoms: Dict[str, Atom], execution_levels: List[List[str]]):
        self.graph = graph
        self.atoms = atoms
        self.execution_levels = execution_levels
    
    def get_atom_dependencies(self, atom_id: str) -> List[str]:
        """Get IDs of atoms this atom depends on"""
        if atom_id not in self.graph:
            return []
        return list(self.graph.predecessors(atom_id))
    
    def get_dependent_atoms(self, atom_id: str) -> List[str]:
        """Get IDs of atoms that depend on this atom"""
        if atom_id not in self.graph:
            return []
        return list(self.graph.successors(atom_id))