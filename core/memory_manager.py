import json
import os
from pathlib import Path
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, base_path="memory"):
        self.base_path = Path(base_path)
        self._init_storage()
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        self.index = faiss.IndexFlatL2(384)
        self._load_vector_index()

    def _init_storage(self):
        directories = {
            'conversations': 'conversations',
            'docs': 'knowledge/docs',
            'tasks': 'tasks',
            'projects': 'projects',
            'index': 'vector_index',
            'sessions': 'sessions'
        }
        
        for name, path in directories.items():
            (self.base_path / path).mkdir(parents=True, exist_ok=True)

    def _load_vector_index(self):
        """Consolidated vector index loading"""
        index_file = self.base_path / "vector_index/index.faiss"
        mapping_file = self.base_path / "vector_index/mapping.csv"
        
        # Initialize empty index if not exists
        if not index_file.exists():
            faiss.write_index(self.index, str(index_file))
            with open(mapping_file, 'w') as f:
                f.write("")
        else:
            self.index = faiss.read_index(str(index_file))
            
        if mapping_file.exists():
            self.mapping = np.loadtxt(mapping_file, delimiter=',', dtype=str)

    def save_document(self, name: str, content: str, metadata: Optional[Dict] = None) -> bool:
        try:
            # Save to knowledge base
            doc_path = self.base_path / f"knowledge/docs/{name}.md"
            doc_path.write_text(content)
            
            # Add to vector index
            emb = self.encoder.encode(content)
            self.index.add(np.array([emb]))
            faiss.write_index(self.index, str(self.base_path / "vector_index/index.faiss"))
            
            # Save mapping
            with open(self.base_path / "vector_index/mapping.csv", 'a') as f:
                f.write(f"{self.index.ntotal - 1},{name}\n")
            
            return True
        except Exception as e:
            logger.error(f"Error saving document: {e}")
            return False

    def search_memory(self, query: str, k=3) -> List[str]:
        emb = self.encoder.encode(query)
        distances, indices = self.index.search(np.array([emb]), k)
        return [self.mapping[i][1] for i in indices[0]]
