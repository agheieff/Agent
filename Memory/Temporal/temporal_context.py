import time
import logging
from typing import List, Dict, Any

from Memory.Graph.memory_graph import MemoryGraph

logger = logging.getLogger(__name__)

class TemporalContext:
    """
    Manages temporal relationships between memory nodes.
    Allows for retrieving nodes based on time windows and sequences.
    """
    
    def __init__(self, memory_graph: MemoryGraph):
        self.graph = memory_graph
        self.time_windows = {
            'recent': 24 * 3600,
            'day': 24 * 3600,
            'week': 7 * 24 * 3600,
            'month': 30 * 24 * 3600
        }
        
    def get_temporal_context(self, window: str = 'recent') -> List[dict]:
        """
        Get memory nodes that were accessed within the specified time window.
        
        Args:
            window: Time window identifier (recent, day, week, month)
            
        Returns:
            List of memory nodes
        """
        if window not in self.time_windows:
            raise ValueError(f"Invalid time window: {window}")
        cutoff = time.time() - self.time_windows[window]
        return [
            node for node in self.graph.graph.nodes.values()
            if node.get('last_accessed', 0) > cutoff
        ]
        
    def get_temporal_relations(self, node_id: str, window: str = 'recent') -> List[dict]:
        """
        Get memory nodes that were accessed around the same time as the specified node.
        
        Args:
            node_id: ID of the reference node
            window: Time window identifier (recent, day, week, month)
            
        Returns:
            List of temporally related memory nodes
        """
        if window not in self.time_windows:
            raise ValueError(f"Invalid time window: {window}")
        cutoff = time.time() - self.time_windows[window]
        node = self.graph.graph.nodes.get(node_id)
        if not node:
            return []
        node_time = node.get('last_accessed', 0)
        related = []
        for other_id, other in self.graph.graph.nodes.items():
            if other_id == node_id:
                continue
            other_time = other.get('last_accessed', 0)
            if abs(other_time - node_time) <= self.time_windows[window]:
                related.append(other)
        return related
        
    def get_temporal_sequence(self, start_time: float, end_time: float) -> List[dict]:
        """
        Get memory nodes accessed within a specific time range, in chronological order.
        
        Args:
            start_time: Start time (epoch timestamp)
            end_time: End time (epoch timestamp)
            
        Returns:
            List of memory nodes in temporal sequence
        """
        return sorted(
            [
                node for node in self.graph.graph.nodes.values()
                if start_time <= node.get('last_accessed', 0) <= end_time
            ],
            key=lambda x: x.get('last_accessed', 0)
        )