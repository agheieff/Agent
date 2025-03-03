"""
Atom of Thoughts (AoT) module for Agent system.
Implements a Markov-based reasoning approach where problems are decomposed
into atomic units that can be processed independently.
"""

from Core.aot.atom_types import AtomType, AtomStatus, Atom, AtomResult, AtomDAG
from Core.aot.atom_decomposer import AtomDecomposer
from Core.aot.dag_manager import DAGManager
from Core.aot.atom_executor import AtomExecutor
from Core.aot.atom_contractor import AtomContractor

__all__ = [
    "AtomType",
    "AtomStatus",
    "Atom",
    "AtomResult",
    "AtomDAG",
    "AtomDecomposer",
    "DAGManager",
    "AtomExecutor",
    "AtomContractor",
]