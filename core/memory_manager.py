import json
import os
from pathlib import Path
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Union
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import networkx as nx
from dataclasses import dataclass, asdict
import hashlib
import time
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
    references: List[str] = None
    metadata: Dict[str, Any] = None
    category_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> 'MemoryNode':
        return MemoryNode(**data)

class MemoryGraph:
    """Implements a Zettelkasten-style knowledge graph"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.graph = nx.DiGraph()
        self._load_graph()
    
    def _load_graph(self):
        """Load graph from disk"""
        graph_file = self.storage_path / "graph.json"
        if graph_file.exists():
            try:
                with open(graph_file, 'r') as f:
                    data = json.load(f)
                    
                # Reconstruct graph
                for node_data in data['nodes']:
                    node = MemoryNode.from_dict(node_data)
                    self.graph.add_node(node.id, **node.to_dict())
                    
                for edge in data['edges']:
                    self.graph.add_edge(edge['source'], edge['target'], **edge.get('metadata', {}))
                    
            except Exception as e:
                logger.error(f"Error loading memory graph: {e}")
                self.graph = nx.DiGraph()
    
    def _save_graph(self):
        """Save graph to disk"""
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
    
    def add_node(self, title: str, content: str, type: str, tags: List[str] = None,
                references: List[str] = None, metadata: Dict = None,
                category_id: Optional[str] = None) -> str:
        """Add a new node to the graph"""
        # Generate unique ID
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
        
        # Add references
        if references:
            for ref in references:
                if ref in self.graph:
                    self.graph.add_edge(node_id, ref, type='reference')
        
        self._save_graph()
        return node_id
    
    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        """Get a node by ID"""
        if node_id in self.graph:
            data = self.graph.nodes[node_id]
            data['last_accessed'] = time.time()
            self.graph.nodes[node_id].update(data)
            self._save_graph()
            return MemoryNode.from_dict(data)
        return None
    
    def update_node(self, node_id: str, **updates) -> bool:
        """Update a node's attributes"""
        if node_id in self.graph:
            data = self.graph.nodes[node_id]
            data.update(updates)
            data['last_accessed'] = time.time()
            self.graph.nodes[node_id].update(data)
            self._save_graph()
            return True
        return False
    
    def find_nodes(self, query: Dict[str, Any]) -> List[MemoryNode]:
        """Find nodes matching query criteria"""
        results = []
        for node_id in self.graph.nodes:
            node_data = self.graph.nodes[node_id]
            matches = all(
                node_data.get(key) == value
                for key, value in query.items()
            )
            if matches:
                results.append(MemoryNode.from_dict(node_data))
        return results
    
    def get_related_nodes(self, node_id: str, max_depth: int = 2) -> List[MemoryNode]:
        """Get related nodes up to max_depth away"""
        if node_id not in self.graph:
            return []
            
        related = set()
        current_nodes = {node_id}
        
        for _ in range(max_depth):
            next_nodes = set()
            for current in current_nodes:
                # Get successors and predecessors
                next_nodes.update(self.graph.successors(current))
                next_nodes.update(self.graph.predecessors(current))
            
            related.update(next_nodes)
            current_nodes = next_nodes
            
        return [
            MemoryNode.from_dict(self.graph.nodes[node_id])
            for node_id in related
        ]

class MemoryManager:
    """Enhanced memory manager with graph-based storage and hierarchical organization"""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or Path("memory")
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize storage directories
        for dir_name in ['documents', 'conversations', 'vector_index', 'temporal', 'commands']:
            (self.base_path / dir_name).mkdir(exist_ok=True)
            
        self.graph = MemoryGraph(self.base_path)
        self.hierarchy = MemoryHierarchy(self.base_path)
        
    def save_document(self, title: str, content: str, tags: List[str] = None,
                     metadata: Dict = None, category_id: Optional[str] = None) -> str:
        """Save a document to memory"""
        try:
            # Save to graph
            node_id = self.graph.add_node(
                title=title,
                content=content,
                type='document',
                tags=tags,
                metadata=metadata,
                category_id=category_id
            )
            
            # Also save to filesystem for backup
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
            return None
            
    def save_conversation(self, conversation_id: str, messages: List[Dict],
                         metadata: Dict = None, category_id: Optional[str] = None) -> str:
        """Save a conversation to memory"""
        try:
            content = json.dumps(messages, indent=2)
            
            # Save to graph
            node_id = self.graph.add_node(
                title=f"Conversation {conversation_id}",
                content=content,
                type='conversation',
                metadata=metadata,
                category_id=category_id
            )
            
            # Also save to filesystem
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
            return None
            
    def get_temporal_context(self, window_minutes: int = 60) -> Dict[str, Any]:
        """Get temporal context of recent activity"""
        try:
            now = time.time()
            window_start = now - (window_minutes * 60)
            
            recent_nodes = [
                node for node in self.graph.graph.nodes.values()
                if node['created_at'] >= window_start
            ]
            
            return {
                'recent_documents': [
                    node for node in recent_nodes
                    if node['type'] == 'document'
                ],
                'recent_conversations': [
                    node for node in recent_nodes
                    if node['type'] == 'conversation'
                ],
                'activity_summary': {
                    'total_nodes': len(recent_nodes),
                    'by_type': {
                        node_type: len([n for n in recent_nodes if n['type'] == node_type])
                        for node_type in set(n['type'] for n in recent_nodes)
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting temporal context: {e}")
            return {}
            
    def search_memory(self, query: str, limit: int = 10,
                     category_id: Optional[str] = None) -> List[Dict]:
        """Search memory using graph traversal and temporal context"""
        try:
            # First get temporal context
            temporal = self.get_temporal_context()
            
            # Then search graph
            results = []
            for node in self.graph.graph.nodes.values():
                # Filter by category if specified
                if category_id and node.get('category_id') != category_id:
                    continue
                    
                if query.lower() in node['title'].lower() or query.lower() in node['content'].lower():
                    # Calculate relevance score
                    recency_score = 1.0 / (1.0 + (time.time() - node['created_at']))
                    
                    # Boost score if node is in recent temporal context
                    if node['id'] in [n['id'] for n in temporal['recent_documents']]:
                        recency_score *= 2
                        
                    # Boost score if node has category
                    if node.get('category_id'):
                        recency_score *= 1.5
                        
                    results.append({
                        'node': node,
                        'score': recency_score
                    })
                    
            # Sort by score and return top results
            results.sort(key=lambda x: x['score'], reverse=True)
            return [r['node'] for r in results[:limit]]
            
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []
            
    def get_category_contents(self, category_id: str,
                            recursive: bool = False) -> List[MemoryNode]:
        """Get all memory nodes in a category"""
        try:
            if recursive:
                # Get all subcategories
                subcats = self.hierarchy.get_subcategories(category_id, recursive=True)
                category_ids = [cat.id for cat in subcats] + [category_id]
            else:
                category_ids = [category_id]
                
            return [
                MemoryNode.from_dict(node)
                for node in self.graph.graph.nodes.values()
                if node.get('category_id') in category_ids
            ]
            
        except Exception as e:
            logger.error(f"Error getting category contents: {e}")
            return []
            
    def move_to_category(self, node_id: str, category_id: str) -> bool:
        """Move a node to a different category"""
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
        """Get category path for a node"""
        try:
            node = self.graph.get_node(node_id)
            if not node or not node.category_id:
                return []
                
            categories = self.hierarchy.get_category_path(node.category_id)
            return [cat.name for cat in categories]
            
        except Exception as e:
            logger.error(f"Error getting node path: {e}")
            return []
