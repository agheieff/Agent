import json
import os
from pathlib import Path
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
import time
import hashlib
import networkx as nx
from dataclasses import dataclass, asdict

from .memory_hierarchy import MemoryHierarchy
from .command_manager import CommandManager

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
    
class TemporalContext:
    def __init__(self, memory_graph: MemoryGraph):
        self.graph = memory_graph
        self.time_windows = {
            'recent': 24 * 3600,
            'day': 24 * 3600,
            'week': 7 * 24 * 3600,
            'month': 30 * 24 * 3600
        }
        
    def get_temporal_context(self, window: str = 'recent') -> List[dict]:
        if window not in self.time_windows:
            raise ValueError(f"Invalid time window: {window}")
        cutoff = time.time() - self.time_windows[window]
        return [
            node for node in self.graph.graph.nodes.values()
            if node.get('last_accessed', 0) > cutoff
        ]
        
    def get_temporal_relations(self, node_id: str, window: str = 'recent') -> List[dict]:
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
        return sorted(
            [
                node for node in self.graph.graph.nodes.values()
                if start_time <= node.get('last_accessed', 0) <= end_time
            ],
            key=lambda x: x.get('last_accessed', 0)
        )

class MemoryPreloader:
    """Handles preloading of relevant memory context"""
    def __init__(self, memory_manager: 'MemoryManager'):
        self.memory_manager = memory_manager
        self.context_keys = ["system_config", "tool_usage", "error_history", "active_projects"]
        
    def initialize_session(self):
        """No-op placeholder in this example"""
        pass

    def get_session_context(self) -> str:
        context = []
        for key in self.context_keys:
            results = self.memory_manager.search_memory(key, limit=3)
            if results:
                context.append(f"## {key.title()}")
                context.extend([n['content'] for n in results[:3]])
        return "\n".join(context)

class MemoryManager:
    """High-level memory manager that composes a MemoryGraph + MemoryHierarchy + TemporalContext"""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path("memory")
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        for d in ['documents', 'conversations', 'vector_index', 'temporal', 'commands']:
            (self.base_path / d).mkdir(exist_ok=True)
            
        self.graph = MemoryGraph(self.base_path)
        self.hierarchy = MemoryHierarchy(self.base_path)
        self.temporal = TemporalContext(self.graph)
        self.command_history: List[Dict] = []
        
    def save_document(self, title: str, content: str,
                      tags: List[str] = None,
                      metadata: Dict = None,
                      category_id: Optional[str] = None) -> str:
        try:
            node_id = self.graph.add_node(
                title=title,
                content=content,
                type='document',
                tags=tags,
                metadata=metadata,
                category_id=category_id
            )
            doc_path = self.base_path / "documents" / f"{node_id}.json"
            with open(doc_path, 'w') as f:
                json.dump({
                    'title': title,
                    'content': content,
                    'tags': tags or [],
                    'metadata': metadata or {},
                    'category_id': category_id,
                    'created_at': datetime.now().isoformat()
                }, f, indent=2)
            return node_id
        except Exception as e:
            logger.error(f"Error saving document: {e}")
            return ""
            
    def save_conversation(self, conversation_id: str, messages: List[Dict],
                          metadata: Dict = None, category_id: Optional[str] = None) -> str:
        try:
            content = json.dumps(messages, indent=2)
            node_id = self.graph.add_node(
                title=f"Conversation {conversation_id}",
                content=content,
                type='conversation',
                metadata=metadata,
                category_id=category_id
            )
            conv_path = self.base_path / "conversations" / f"{conversation_id}.json"
            with open(conv_path, 'w') as f:
                json.dump({
                    'messages': messages,
                    'metadata': metadata or {},
                    'category_id': category_id,
                    'created_at': datetime.now().isoformat()
                }, f, indent=2)
            return node_id
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return ""
            
    def get_execution_context(self, window_minutes: int = 60) -> str:
        try:
            now = time.time()
            window_start = now - (window_minutes * 60)
            recent_nodes = [
                node for node in self.graph.graph.nodes.values()
                if node['created_at'] >= window_start
            ]
            info = {
                'recent_documents': [n for n in recent_nodes if n['type'] == 'document'],
                'recent_conversations': [n for n in recent_nodes if n['type'] == 'conversation'],
                'activity_summary': {
                    'total_nodes': len(recent_nodes),
                    'by_type': {}
                }
            }
            types = set(n['type'] for n in recent_nodes)
            for t in types:
                info['activity_summary']['by_type'][t] = len([n for n in recent_nodes if n['type'] == t])
            return json.dumps(info, indent=2)
        except Exception as e:
            logger.error(f"Error getting execution context: {e}")
            return ""
            
    def search_memory(self, query: str, limit: int = 10, category_id: Optional[str] = None) -> List[dict]:
        try:
            # Very naive approach: we simply check if query is in the title or content
            matches = []
            for node_id in self.graph.graph.nodes:
                node = self.graph.graph.nodes[node_id]
                if category_id and node.get('category_id') != category_id:
                    continue
                if (query.lower() in node.get('title','').lower()
                    or query.lower() in node.get('content','').lower()):
                    matches.append(node)
            # Sort by recency
            matches.sort(key=lambda x: x.get('last_accessed', 0), reverse=True)
            return matches[:limit]
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []
            
    def get_category_contents(self, category_id: str, recursive: bool = False) -> List[MemoryNode]:
        try:
            if recursive:
                subcats = self.hierarchy.get_subcategories(category_id, recursive=True)
                cat_ids = [c.id for c in subcats] + [category_id]
            else:
                cat_ids = [category_id]
            return [
                MemoryNode.from_dict(n)
                for n in self.graph.graph.nodes.values()
                if n.get('category_id') in cat_ids
            ]
        except Exception as e:
            logger.error(f"Error getting category contents: {e}")
            return []
            
    def move_to_category(self, node_id: str, category_id: str) -> bool:
        try:
            if node_id not in self.graph.graph:
                return False
            if not self.hierarchy.get_category(category_id):
                return False
            return self.graph.update_node(node_id, category_id=category_id)
        except Exception as e:
            logger.error(f"Error moving node to category: {e}")
            return False
            
    def get_node_path(self, node_id: str) -> List[str]:
        try:
            node = self.graph.get_node(node_id)
            if not node or not node.category_id:
                return []
            categories = self.hierarchy.get_category_path(node.category_id)
            return [cat.name for cat in categories]
        except Exception as e:
            logger.error(f"Error getting node path: {e}")
            return []
            
    def get_recent_context(self, hours: int = 24) -> List[dict]:
        return self.temporal.get_temporal_context(f"{hours}h")
        
    def get_related_in_timeframe(self, node_id: str, hours: int = 24) -> List[dict]:
        return self.temporal.get_temporal_relations(node_id, f"{hours}h")
        
    def get_activity_sequence(self, start_time: float, end_time: float) -> List[dict]:
        return self.temporal.get_temporal_sequence(start_time, end_time)

    def add_command_to_history(self, command: str, shell: str, success: bool = True):
        self.command_history.append({
            'command': command,
            'shell': shell,
            'success': success,
            'timestamp': time.time()
        })
        # Keep last 1000
        if len(self.command_history) > 1000:
            self.command_history = self.command_history[-1000:]
