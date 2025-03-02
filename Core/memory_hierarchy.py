import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import time
import networkx as nx
from pathlib import Path
import json
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class MemoryCategory:
    """Represents a category in the memory hierarchy"""
    id: str
    name: str
    description: str
    parent_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_modified: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'parent_id': self.parent_id,
            'attributes': self.attributes,
            'created_at': self.created_at,
            'last_modified': self.last_modified
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'MemoryCategory':
        return MemoryCategory(**data)

@dataclass
class MemoryRelation:
    """Represents a relationship between memory nodes"""
    source_id: str
    target_id: str
    relation_type: str
    strength: float
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict:
        return {
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation_type': self.relation_type,
            'strength': self.strength,
            'attributes': self.attributes,
            'created_at': self.created_at,
            'last_accessed': self.last_accessed
        }
    
    @staticmethod
    def from_dict(data: Dict) -> 'MemoryRelation':
        return MemoryRelation(**data)

class MemoryHierarchy:
    """Manages hierarchical organization of memory"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.category_graph = nx.DiGraph()
        self.relation_graph = nx.Graph()
        self._load_hierarchy()
        
    def _load_hierarchy(self):
        try:
            cat_file = self.storage_path / "categories.json"
            if cat_file.exists():
                with open(cat_file, 'r') as f:
                    data = json.load(f)
                    for cat_data in data:
                        category = MemoryCategory.from_dict(cat_data)
                        self.category_graph.add_node(category.id, category=category)
                        if category.parent_id:
                            self.category_graph.add_edge(category.parent_id, category.id)
                            
            rel_file = self.storage_path / "relations.json"
            if rel_file.exists():
                with open(rel_file, 'r') as f:
                    data = json.load(f)
                    for rel_data in data:
                        relation = MemoryRelation.from_dict(rel_data)
                        self.relation_graph.add_edge(
                            relation.source_id,
                            relation.target_id,
                            relation=relation
                        )
                        
        except Exception as e:
            logger.error(f"Error loading hierarchy: {e}")
            
    def _save_hierarchy(self):
        try:
            categories = [
                self.category_graph.nodes[node]['category'].to_dict()
                for node in self.category_graph.nodes
            ]
            with open(self.storage_path / "categories.json", 'w') as f:
                json.dump(categories, f, indent=2)
                
            relations = [
                self.relation_graph.edges[edge]['relation'].to_dict()
                for edge in self.relation_graph.edges
            ]
            with open(self.storage_path / "relations.json", 'w') as f:
                json.dump(relations, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving hierarchy: {e}")
            
    def add_category(self, name: str, description: str,
                     parent_id: Optional[str] = None,
                     attributes: Dict[str, Any] = None) -> str:
        category = MemoryCategory(
            id=f"cat_{int(time.time())}",
            name=name,
            description=description,
            parent_id=parent_id,
            attributes=attributes or {}
        )
        self.category_graph.add_node(category.id, category=category)
        if parent_id and parent_id in self.category_graph:
            self.category_graph.add_edge(parent_id, category.id)
        self._save_hierarchy()
        return category.id
        
    def add_relation(self, source_id: str, target_id: str,
                     relation_type: str, strength: float = 1.0,
                     attributes: Dict[str, Any] = None) -> bool:
        if source_id not in self.relation_graph or target_id not in self.relation_graph:
            # Could add a check or auto-add, but here we just fail
            return False
            
        relation = MemoryRelation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=strength,
            attributes=attributes or {}
        )
        self.relation_graph.add_edge(source_id, target_id, relation=relation)
        self._save_hierarchy()
        return True
        
    def get_category(self, category_id: str) -> Optional[MemoryCategory]:
        if category_id in self.category_graph:
            return self.category_graph.nodes[category_id]['category']
        return None
        
    def get_subcategories(self, category_id: str, recursive: bool = False) -> List[MemoryCategory]:
        if category_id not in self.category_graph:
            return []
        if recursive:
            descendants = nx.descendants(self.category_graph, category_id)
            return [self.category_graph.nodes[node]['category'] for node in descendants]
        else:
            return [self.category_graph.nodes[succ]['category'] for succ in self.category_graph.successors(category_id)]
            
    def get_category_path(self, category_id: str) -> List[MemoryCategory]:
        if category_id not in self.category_graph:
            return []
        path = []
        current = category_id
        while current is not None:
            category = self.category_graph.nodes[current]['category']
            path.append(category)
            current = category.parent_id
        return list(reversed(path))
        
    def get_related_nodes(self, node_id: str,
                          relation_types: Optional[List[str]] = None,
                          min_strength: float = 0.0) -> List[Dict]:
        if node_id not in self.relation_graph:
            return []
        related = []
        for neighbor in self.relation_graph.neighbors(node_id):
            relation = self.relation_graph.edges[node_id, neighbor]['relation']
            if relation_types and relation.relation_type not in relation_types:
                continue
            if relation.strength < min_strength:
                continue
            related.append({
                'node_id': neighbor,
                'relation': relation.to_dict()
            })
        return related
        
    def strengthen_relation(self, source_id: str, target_id: str,
                            amount: float = 0.1) -> bool:
        if not self.relation_graph.has_edge(source_id, target_id):
            return False
        relation = self.relation_graph.edges[source_id, target_id]['relation']
        relation.strength = min(1.0, relation.strength + amount)
        relation.last_accessed = time.time()
        self._save_hierarchy()
        return True
        
    def get_category_stats(self, category_id: str) -> Dict[str, Any]:
        if category_id not in self.category_graph:
            return {}
        category = self.category_graph.nodes[category_id]['category']
        subcats = self.get_subcategories(category_id, recursive=True)
        return {
            'name': category.name,
            'total_subcategories': len(subcats),
            'direct_subcategories': len(list(self.category_graph.successors(category_id))),
            'depth': len(self.get_category_path(category_id)),
            'created_at': datetime.fromtimestamp(category.created_at).isoformat(),
            'last_modified': datetime.fromtimestamp(category.last_modified).isoformat()
        }
        
    def merge_categories(self, source_id: str, target_id: str) -> bool:
        if (source_id not in self.category_graph or
            target_id not in self.category_graph):
            return False
        try:
            for succ in list(self.category_graph.successors(source_id)):
                self.category_graph.remove_edge(source_id, succ)
                self.category_graph.add_edge(target_id, succ)
                succ_cat = self.category_graph.nodes[succ]['category']
                succ_cat.parent_id = target_id
            for edge in list(self.relation_graph.edges(source_id)):
                relation = self.relation_graph.edges[edge]['relation']
                if edge[0] == source_id:
                    new_source = target_id
                    new_target = edge[1]
                else:
                    new_source = edge[0]
                    new_target = target_id
                self.relation_graph.remove_edge(*edge)
                self.relation_graph.add_edge(new_source, new_target, relation=relation)
            self.category_graph.remove_node(source_id)
            self._save_hierarchy()
            return True
        except Exception as e:
            logger.error(f"Error merging categories: {e}")
            return False
