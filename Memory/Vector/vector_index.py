import os
import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from sentence_transformers import SentenceTransformer
import faiss

logger = logging.getLogger(__name__)

class VectorIndex:
    """Implements vector-based semantic search for memory items"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.vector_index_path = self.storage_path / "vector_index"
        self.vector_index_path.mkdir(exist_ok=True)
        
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.dimension = self.model.get_sentence_embedding_dimension()
            self.index = None
            self.node_ids = []
            self._load_or_create_index()
        except Exception as e:
            logger.error(f"Error initializing vector index: {e}")
            self.model = None
            self.index = None
    
    def _load_or_create_index(self):
        index_file = self.vector_index_path / "faiss.index"
        ids_file = self.vector_index_path / "node_ids.json"
        
        if index_file.exists() and ids_file.exists():
            try:
                self.index = faiss.read_index(str(index_file))
                with open(ids_file, 'r') as f:
                    self.node_ids = json.load(f)
                logger.info(f"Loaded vector index with {len(self.node_ids)} entries")
            except Exception as e:
                logger.error(f"Error loading vector index: {e}")
                self._create_new_index()
        else:
            self._create_new_index()
    
    def _create_new_index(self):
        try:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.node_ids = []
            logger.info("Created new vector index")
        except Exception as e:
            logger.error(f"Error creating vector index: {e}")
    
    def _save_index(self):
        try:
            if self.index is None:
                return
            index_file = self.vector_index_path / "faiss.index"
            ids_file = self.vector_index_path / "node_ids.json"
            
            if index_file.exists():
                backup_file = self.vector_index_path / "faiss.index.bak"
                os.replace(index_file, backup_file)
            if ids_file.exists():
                backup_ids = self.vector_index_path / "node_ids.json.bak"
                os.replace(ids_file, backup_ids)
            
            faiss.write_index(self.index, str(index_file))
            with open(ids_file, 'w') as f:
                json.dump(self.node_ids, f)
        except Exception as e:
            logger.error(f"Error saving vector index: {e}")
    
    def add_text(self, node_id: str, text: str) -> bool:
        try:
            if self.model is None or self.index is None:
                return False
            if node_id in self.node_ids:
                return True
            embedding = self.model.encode([text])[0]
            embedding = np.array([embedding], dtype=np.float32)
            self.index.add(embedding)
            self.node_ids.append(node_id)
            if len(self.node_ids) % 10 == 0:
                self._save_index()
            return True
        except Exception as e:
            logger.error(f"Error adding text to vector index: {e}")
            return False
    
    def search(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        try:
            if self.model is None or self.index is None or len(self.node_ids) == 0:
                return []
            query_embedding = self.model.encode([query])[0]
            query_embedding = np.array([query_embedding], dtype=np.float32)
            distances, indices = self.index.search(query_embedding, min(k, len(self.node_ids)))
            
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < len(self.node_ids):
                    results.append((self.node_ids[idx], float(distances[0][i])))
            return results
        except Exception as e:
            logger.error(f"Error searching vector index: {e}")
            return []