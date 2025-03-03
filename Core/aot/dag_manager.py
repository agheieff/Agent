"""
DAG Manager for Atom of Thoughts (AoT) module.

This component manages the directed acyclic graph for atom dependencies.
"""

import logging
from typing import List, Dict, Any, Set
import networkx as nx
from Core.aot.atom_types import Atom, AtomDAG

logger = logging.getLogger(__name__)

class DAGManager:
    """Manages the directed acyclic graph for atom dependencies"""
    
    def __init__(self, config=None):
        self.config = config or {}
    
    def create_dag(self, atoms: List[Atom]) -> AtomDAG:
        """
        Create a directed acyclic graph from atoms and their dependencies.
        
        Args:
            atoms: List of Atom objects with dependency information
            
        Returns:
            AtomDAG object representing the execution graph
        """
        # Create a directed graph
        G = nx.DiGraph()
        
        # Add all atoms as nodes
        for atom in atoms:
            G.add_node(atom.id, atom=atom)
        
        # Add edges for dependencies
        for atom in atoms:
            for input_id in atom.inputs:
                if input_id in G:
                    G.add_edge(input_id, atom.id)
        
        # Verify it's a DAG (no cycles)
        if not nx.is_directed_acyclic_graph(G):
            logger.warning("Dependency graph contains cycles! Removing cycles...")
            # Find and remove cycles by breaking at arbitrary points
            try:
                cycles = list(nx.simple_cycles(G))
                for cycle in cycles:
                    if cycle and len(cycle) > 1:
                        # Remove the first edge in the cycle
                        G.remove_edge(cycle[0], cycle[1])
            except Exception as e:
                logger.error(f"Error detecting cycles: {e}")
                # If cycle detection fails, make a fresh graph with no edges
                G = nx.DiGraph()
                for atom in atoms:
                    G.add_node(atom.id, atom=atom)
        
        # Create execution levels (atoms that can be executed in parallel)
        execution_levels = []
        remaining_nodes = set(G.nodes())
        
        while remaining_nodes:
            # Find nodes with no incoming edges from remaining nodes
            level_nodes = [n for n in remaining_nodes if not any(pred in remaining_nodes for pred in G.predecessors(n))]
            
            if not level_nodes:
                # Should not happen in a DAG, but break to avoid infinite loop
                logger.error("Error in DAG level creation! Forcing remaining nodes into a level.")
                level_nodes = list(remaining_nodes)[:1]
            
            execution_levels.append(level_nodes)
            remaining_nodes -= set(level_nodes)
        
        # Build the atom mapping
        atom_dict = {atom.id: atom for atom in atoms}
        
        # Create the AtomDAG object
        atom_dag = AtomDAG(
            graph=G,
            atoms=atom_dict,
            execution_levels=execution_levels
        )
        
        logger.info(f"Created DAG with {len(atoms)} atoms in {len(execution_levels)} execution levels")
        return atom_dag
    
    def get_atom_dependencies(self, atom_id: str, dag: AtomDAG) -> List[str]:
        """Get the IDs of atoms that this atom depends on"""
        if atom_id not in dag.graph:
            return []
        
        return list(dag.graph.predecessors(atom_id))
    
    def get_dependent_atoms(self, atom_id: str, dag: AtomDAG) -> List[str]:
        """Get the IDs of atoms that depend on this atom"""
        if atom_id not in dag.graph:
            return []
        
        return list(dag.graph.successors(atom_id))
    
    def get_execution_order(self, dag: AtomDAG) -> List[str]:
        """Get a valid topological ordering of atoms for execution"""
        try:
            return list(nx.topological_sort(dag.graph))
        except nx.NetworkXUnfeasible:
            # If graph has cycles, use a different approach
            logger.error("Cannot determine topological sort - graph may have cycles.")
            return [level_node for level in dag.execution_levels for level_node in level]