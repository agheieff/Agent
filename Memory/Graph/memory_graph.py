import json
import time
import logging
import networkx as nx
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class MemoryNode:
    """Represents a node in the memory graph"""
    id: str
    title: str
    content: str
    type: str
    tags: List[str]
    created_at: float
    last_accessed: float
    references: List[str]
    metadata: Dict[str, Any]
    category_id: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'MemoryNode':
        return MemoryNode(**data)

class MemoryGraph:
    """Implements a simple knowledge graph for memory"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.graph = nx.DiGraph()
        self._load_graph()
    
    def _load_graph(self):
        graph_file = self.storage_path / "graph.json"
        if graph_file.exists():
            try:
                with open(graph_file, 'r') as f:
                    data = json.load(f)
                for node_data in data['nodes']:
                    self.graph.add_node(node_data['id'], **node_data)
                for edge in data['edges']:
                    self.graph.add_edge(edge['source'], edge['target'], **edge.get('metadata', {}))
            except Exception as e:
                logger.error(f"Error loading memory graph: {e}")
                self.graph = nx.DiGraph()
    
    def _save_graph(self):
        try:
            data = {
                'nodes': [self.graph.nodes[node] for node in self.graph.nodes],
                'edges': [
                    {
                        'source': edge[0],
                        'target': edge[1],
                        'metadata': self.graph.edges[edge]
                    }
                    for edge in self.graph.edges
                ]
            }
            with open(self.storage_path / "graph.json", 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving memory graph: {e}")
    
    def add_node(self,
                 title: str,
                 content: str,
                 type: str,
                 tags: List[str] = None,
                 references: List[str] = None,
                 metadata: Dict[str, Any] = None,
                 category_id: Optional[str] = None) -> str:
        import hashlib
        node_id = hashlib.sha256(f"{title}{time.time()}".encode()).hexdigest()[:12]
        node = MemoryNode(
            id=node_id,
            title=title,
            content=content,
            type=type,
            tags=tags or [],
            created_at=time.time(),
            last_accessed=time.time(),
            references=references or [],
            metadata=metadata or {},
            category_id=category_id
        )
        self.graph.add_node(node_id, **node.to_dict())
        
        if references:
            for ref in references:
                if ref in self.graph:
                    self.graph.add_edge(node_id, ref, type='reference')
        
        self._save_graph()
        return node_id
    
    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        if node_id in self.graph:
            data = self.graph.nodes[node_id]
            data['last_accessed'] = time.time()
            self.graph.nodes[node_id].update(data)
            self._save_graph()
            return MemoryNode.from_dict(data)
        return None
    
    def update_node(self, node_id: str, **updates) -> bool:
        if node_id in self.graph:
            data = self.graph.nodes[node_id]
            data.update(updates)
            data['last_accessed'] = time.time()
            self.graph.nodes[node_id].update(data)
            self._save_graph()
            return True
        return False
    
    def find_nodes(self, query: Dict[str, Any]) -> List[MemoryNode]:
        results = []
        for node_id in self.graph.nodes:
            node_data = self.graph.nodes[node_id]
            matches = all(node_data.get(k) == v for k, v in query.items())
            if matches:
                results.append(MemoryNode.from_dict(node_data))
        return results
    
    def get_related_nodes(self, node_id: str, max_depth: int = 2) -> List[MemoryNode]:
        if node_id not in self.graph:
            return []
        related = set()
        current_nodes = {node_id}
        for _ in range(max_depth):
            next_nodes = set()
            for current in current_nodes:
                next_nodes.update(self.graph.successors(current))
                next_nodes.update(self.graph.predecessors(current))
            related.update(next_nodes)
            current_nodes = next_nodes
        return [MemoryNode.from_dict(self.graph.nodes[n]) for n in related]