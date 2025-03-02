import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import OrderedDict
import numpy as np
import faiss
import time
import json
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Represents a cached memory node"""
    data: Any
    vector: Optional[np.ndarray] = None
    last_accessed: float = 0.0
    access_count: int = 0

class LRUCache:
    """LRU cache implementation with size limit"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: OrderedDict = OrderedDict()
        
    def get(self, key: str) -> Optional[Any]:
        if key not in self.cache:
            return None
        value = self.cache.pop(key)
        self.cache[key] = value
        return value
        
    def put(self, key: str, value: Any):
        if key in self.cache:
            self.cache.pop(key)
        elif len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)
        self.cache[key] = value
        
    def clear(self):
        self.cache.clear()

class VectorIndex:
    """Vector index for semantic search"""
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index = faiss.IndexFlatL2(dimension)
        self.id_map: Dict[int, str] = {}
        self.next_id = 0
        
    def add_vector(self, node_id: str, vector: np.ndarray):
        self.index.add(vector.reshape(1, -1))
        self.id_map[self.next_id] = node_id
        self.next_id += 1
        
    def search(self, query_vector: np.ndarray, k: int = 10) -> List[Tuple[str, float]]:
        distances, indices = self.index.search(query_vector.reshape(1, -1), k)
        
        return [
            (self.id_map[idx], dist)
            for idx, dist in zip(indices[0], distances[0])
            if idx in self.id_map
        ]
        
    def remove_vector(self, node_id: str):
        # FAISS doesn't support direct removal, so we rebuild
        vectors = []
        ids = []
        
        for idx, nid in self.id_map.items():
            if nid != node_id:
                vec = self.index.reconstruct(idx)
                vectors.append(vec)
                ids.append(nid)
        
        self.index = faiss.IndexFlatL2(self.dimension)
        self.id_map = {}
        self.next_id = 0
        
        for vec, nid in zip(vectors, ids):
            self.add_vector(nid, vec)

class MemoryCache:
    """Enhanced memory cache with vector embeddings"""
    
    def __init__(self, storage_path: Path, cache_size: int = 1000):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.node_cache = LRUCache(cache_size)
        self.relation_cache = LRUCache(cache_size)
        
        # This model is CPU-based, but can be replaced with AMD-enabled libraries
        # if you have them installed. No explicit NVIDIA references remain.
        from sentence_transformers import SentenceTransformer
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        
        self.vector_index = VectorIndex()
        
        self._load_cache()
        
    def _load_cache(self):
        try:
            index_file = self.storage_path / "vector_index.faiss"
            if index_file.exists():
                self.vector_index.index = faiss.read_index(str(index_file))
            mapping_file = self.storage_path / "id_mapping.json"
            if mapping_file.exists():
                with open(mapping_file, 'r') as f:
                    self.vector_index.id_map = {
                        int(k): v for k, v in json.load(f).items()
                    }
                self.vector_index.next_id = max(
                    self.vector_index.id_map.keys(), default=-1
                ) + 1
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            
    def _save_cache(self):
        try:
            faiss.write_index(self.vector_index.index, str(self.storage_path / "vector_index.faiss"))
            with open(self.storage_path / "id_mapping.json", 'w') as f:
                json.dump({str(k): v for k, v in self.vector_index.id_map.items()}, f)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            
    def get_node(self, node_id: str) -> Optional[CacheEntry]:
        entry = self.node_cache.get(node_id)
        if entry:
            entry.last_accessed = time.time()
            entry.access_count += 1
        return entry
        
    def add_node(self, node_id: str, data: Any, content: str):
        try:
            vector = self.encoder.encode(content)
            entry = CacheEntry(
                data=data,
                vector=vector,
                last_accessed=time.time(),
                access_count=1
            )
            self.node_cache.put(node_id, entry)
            self.vector_index.add_vector(node_id, vector)
            self._save_cache()
        except Exception as e:
            logger.error(f"Error adding node to cache: {e}")
            
    def remove_node(self, node_id: str):
        try:
            entry = self.node_cache.get(node_id)
            if entry:
                self.node_cache.cache.pop(node_id)
                self.vector_index.remove_vector(node_id)
            self._save_cache()
        except Exception as e:
            logger.error(f"Error removing node from cache: {e}")
            
    def search_similar(self, content: str, k: int = 10) -> List[Tuple[str, float]]:
        try:
            query_vector = self.encoder.encode(content)
            return self.vector_index.search(query_vector, k)
        except Exception as e:
            logger.error(f"Error searching similar nodes: {e}")
            return []
            
    def get_relation(self, relation_id: str) -> Optional[Any]:
        entry = self.relation_cache.get(relation_id)
        if entry:
            entry.last_accessed = time.time()
            entry.access_count += 1
        return entry.data if entry else None
        
    def add_relation(self, relation_id: str, data: Any):
        entry = CacheEntry(
            data=data,
            last_accessed=time.time(),
            access_count=1
        )
        self.relation_cache.put(relation_id, entry)
        
    def clear(self):
        self.node_cache.clear()
        self.relation_cache.clear()
        self.vector_index = VectorIndex()
        self._save_cache()
        
    def get_stats(self) -> Dict[str, Any]:
        return {
            'node_cache_size': len(self.node_cache.cache),
            'relation_cache_size': len(self.relation_cache.cache),
            'vector_index_size': self.vector_index.next_id,
            'most_accessed_nodes': sorted(
                [(nid, entry.access_count) for nid, entry in self.node_cache.cache.items()],
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }
