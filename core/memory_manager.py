import json
import os
import re
import shutil
import math
from pathlib import Path
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple, Union, Set
import time
import hashlib
import networkx as nx
from dataclasses import dataclass, asdict
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

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

class VectorIndex:
    """Implements vector-based semantic search for memory items"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.vector_index_path = storage_path / "vector_index"
        self.vector_index_path.mkdir(exist_ok=True)
        
        # Initialize the sentence transformer model
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.dimension = self.model.get_sentence_embedding_dimension()
            self.index = None
            self.node_ids = []
            self._load_or_create_index()
        except Exception as e:
            logger.error(f"Error initializing vector index: {e}")
            # Fallback to avoid breaking the agent if vector search can't initialize
            self.model = None
            self.index = None
    
    def _load_or_create_index(self):
        """Load existing index or create a new one"""
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
        """Create a new FAISS index"""
        try:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.node_ids = []
            logger.info("Created new vector index")
        except Exception as e:
            logger.error(f"Error creating vector index: {e}")
    
    def _save_index(self):
        """Save the index and node IDs to disk"""
        try:
            if self.index is None:
                return
                
            index_file = self.vector_index_path / "faiss.index"
            ids_file = self.vector_index_path / "node_ids.json"
            
            # Create a backup first
            if index_file.exists():
                backup_file = self.vector_index_path / f"faiss.index.bak"
                os.replace(index_file, backup_file)
            
            if ids_file.exists():
                backup_ids = self.vector_index_path / f"node_ids.json.bak"
                os.replace(ids_file, backup_ids)
                
            faiss.write_index(self.index, str(index_file))
            with open(ids_file, 'w') as f:
                json.dump(self.node_ids, f)
            logger.info(f"Saved vector index with {len(self.node_ids)} entries")
        except Exception as e:
            logger.error(f"Error saving vector index: {e}")
    
    def add_text(self, node_id: str, text: str) -> bool:
        """Add text to the vector index"""
        try:
            if self.model is None or self.index is None:
                return False
                
            # Check if node_id already exists
            if node_id in self.node_ids:
                return True  # Already indexed
                
            # Encode the text
            embedding = self.model.encode([text])[0]
            embedding = np.array([embedding], dtype=np.float32)
            
            # Add to index
            self.index.add(embedding)
            self.node_ids.append(node_id)
            
            # Save periodically (e.g., every 10 entries)
            if len(self.node_ids) % 10 == 0:
                self._save_index()
                
            return True
        except Exception as e:
            logger.error(f"Error adding text to vector index: {e}")
            return False
    
    def search(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        """Search for similar texts based on vector similarity"""
        try:
            if self.model is None or self.index is None or len(self.node_ids) == 0:
                return []
                
            # Encode the query
            query_embedding = self.model.encode([query])[0]
            query_embedding = np.array([query_embedding], dtype=np.float32)
            
            # Search
            distances, indices = self.index.search(query_embedding, min(k, len(self.node_ids)))
            
            # Return node_ids and distances
            results = []
            for i, idx in enumerate(indices[0]):
                if idx < len(self.node_ids):
                    results.append((self.node_ids[idx], float(distances[0][i])))
            
            return results
        except Exception as e:
            logger.error(f"Error searching vector index: {e}")
            return []

class MemoryManager:
    """High-level memory manager that composes a MemoryGraph + MemoryHierarchy + TemporalContext + VectorIndex"""
    
    def __init__(self, base_path: Path = None):
        # If no path provided, use the configuration from memory.config file
        if base_path is None:
            base_path = self._get_configured_path()
        
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Save the configured path
        self._save_configured_path(self.base_path)
    
    def _get_configured_path(self) -> Path:
        """Read memory location from configuration file"""
        # Look for memory.config in the current working directory and agent directory
        config_paths = [
            Path.cwd() / "memory.config",
            Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "memory.config"
        ]
        
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r') as f:
                        memory_path = f.read().strip()
                        if memory_path:
                            return Path(memory_path)
                except:
                    pass
        
        # If not found, check environment variable
        memory_dir = os.environ.get("AGENT_MEMORY_DIR")
        if memory_dir:
            return Path(memory_dir)
        
        # If still not found, use default locations
        agent_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Try these locations in order:
        # 1. ../AgentMemory (relative to agent code)
        # 2. ./memory (in current directory)
        # 3. ./AgentMemory (in current directory)
        for path_option in [agent_dir.parent / "AgentMemory", Path.cwd() / "memory", Path.cwd() / "AgentMemory"]:
            if path_option.exists() or path_option.parent.exists():
                return path_option
                
        # Default to memory in the agent directory
        return agent_dir / "memory"
        
    def _save_configured_path(self, path: Path):
        """Save memory location to configuration file"""
        try:
            agent_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = agent_dir / "memory.config"
            
            with open(config_path, 'w') as f:
                f.write(str(path))
        except Exception as e:
            logger.error(f"Error saving memory configuration: {e}")
        
        # Create all required directories
        for d in ['documents', 'conversations', 'vector_index', 'temporal', 'commands', 'backups',
                  'tasks', 'reflections', 'notes', 'working_memory', 'archive']:
            (self.base_path / d).mkdir(exist_ok=True)
            
        self.graph = MemoryGraph(self.base_path)
        self.hierarchy = MemoryHierarchy(self.base_path)
        self.temporal = TemporalContext(self.graph)
        self.vector_index = VectorIndex(self.base_path)
        self.command_history: List[Dict] = []
        self.memory_stats = {
            'nodes_added': 0,
            'documents_saved': 0,
            'conversations_saved': 0,
            'last_backup_time': 0,
            'searches_performed': 0
        }
        
        # Initialize memory indexing limits
        self.memory_limits = {
            'max_document_size': 1024 * 1024,  # 1MB
            'max_indexed_entries': 10000,
            'max_backups': 10, 
            'backup_interval': 3600  # 1 hour
        }
        
        # Load existing command history if available
        self._load_command_history()
        
        # Perform recovery check on startup
        self._check_for_recovery()
        
        # Clean up old temp files on startup
        self._cleanup_temp_files()
        
    def save_document(self, title: str, content: str,
                      tags: List[str] = None,
                      metadata: Dict = None,
                      category_id: Optional[str] = None,
                      permanent: bool = False) -> str:
        """
        Save a document to memory, both in the graph and as a file
        
        Args:
            title: Document title
            content: Document content
            tags: List of tags for categorization
            metadata: Additional metadata
            category_id: Category ID if part of hierarchy
            permanent: If True, mark as permanent (won't be auto-pruned)
            
        Returns:
            Node ID of the saved document
        """
        try:
            # Truncate content if it's too large
            if len(content) > self.memory_limits['max_document_size']:
                original_size = len(content)
                content = content[:self.memory_limits['max_document_size']] + "\n...[CONTENT TRUNCATED]"
                logger.warning(f"Document '{title}' truncated from {original_size} to {len(content)} bytes")
                
                if metadata is None:
                    metadata = {}
                metadata['truncated'] = True
                metadata['original_size'] = original_size
            
            # Add persistence flag to metadata if permanent
            if permanent:
                if metadata is None:
                    metadata = {}
                metadata['permanent'] = True
            
            # Add timestamp to metadata
            if metadata is None:
                metadata = {}
            timestamp = time.time()
            metadata['timestamp'] = timestamp
            metadata['created_at'] = datetime.now().isoformat()
            
            # Create node in memory graph
            node_id = self.graph.add_node(
                title=title,
                content=content,
                type='document',
                tags=tags or [],
                metadata=metadata,
                category_id=category_id
            )
            
            # Save to disk
            doc_path = self.base_path / "documents" / f"{node_id}.json"
            with open(doc_path, 'w') as f:
                json.dump({
                    'id': node_id,
                    'title': title,
                    'content': content,
                    'tags': tags or [],
                    'metadata': metadata,
                    'category_id': category_id,
                    'type': 'document',
                    'created_at': metadata['created_at']
                }, f, indent=2)
                
            # Add to vector index
            self.vector_index.add_text(node_id, f"{title}\n{content}")
            
            # Update statistics
            self.memory_stats['nodes_added'] += 1
            self.memory_stats['documents_saved'] += 1
            
            # Create a backup periodically
            if (self.memory_stats['nodes_added'] % 10 == 0 or 
                permanent or 
                'important' in (tags or [])):
                self.create_backup()
                
            return node_id
        except Exception as e:
            logger.error(f"Error saving document: {e}")
            return ""
            
    def save_conversation(self, conversation_id: str, messages: List[Dict],
                          metadata: Dict = None, category_id: Optional[str] = None) -> str:
        try:
            # Create a summary of the conversation for vector search
            summary = self._summarize_conversation(messages)
            
            # Store the full conversation as JSON
            content = json.dumps(messages, indent=2)
            
            # Create node
            node_id = self.graph.add_node(
                title=f"Conversation {conversation_id}",
                content=content,
                type='conversation',
                metadata={**(metadata or {}), 'summary': summary},
                category_id=category_id
            )
            
            # Save to disk
            conv_path = self.base_path / "conversations" / f"{conversation_id}.json"
            with open(conv_path, 'w') as f:
                json.dump({
                    'messages': messages,
                    'metadata': {**(metadata or {}), 'summary': summary},
                    'category_id': category_id,
                    'created_at': datetime.now().isoformat()
                }, f, indent=2)
            
            # Add to vector index
            self.vector_index.add_text(node_id, summary)
            
            # Create a backup periodically
            if len(self.graph.graph.nodes) % 10 == 0:
                self.create_backup()
            
            return node_id
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return ""
            
    def _summarize_conversation(self, messages: List[Dict]) -> str:
        """Create a simple summary of the conversation for vector search"""
        try:
            # Extract all user messages
            user_msgs = [m['content'] for m in messages if m.get('role') == 'user']
            
            # Extract all assistant messages
            assistant_msgs = [m['content'] for m in messages if m.get('role') == 'assistant']
            
            # Create a basic summary including main points
            summary_parts = []
            if user_msgs:
                summary_parts.append("User asked about: " + "; ".join(user_msgs[:3]))
            
            if assistant_msgs:
                # Get first and last message to capture initial response and conclusion
                if len(assistant_msgs) >= 2:
                    summary_parts.append("Assistant initially responded: " + assistant_msgs[0][:200])
                    summary_parts.append("Assistant concluded with: " + assistant_msgs[-1][:200])
                elif len(assistant_msgs) == 1:
                    summary_parts.append("Assistant responded: " + assistant_msgs[0][:300])
            
            # Extract commands if present
            commands = []
            command_pattern = r"<(bash|python)>(.*?)</\1>"
            for msg in assistant_msgs:
                matches = re.finditer(command_pattern, msg, re.DOTALL)
                for match in matches:
                    cmd_type, cmd = match.groups()
                    commands.append(f"{cmd_type}: {cmd.strip()}")
            
            if commands:
                summary_parts.append("Commands executed: " + "; ".join(commands[:5]))
            
            return "\n".join(summary_parts)
        except Exception as e:
            logger.error(f"Error summarizing conversation: {e}")
            return "Conversation " + datetime.now().isoformat()
            
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
            
    def _check_for_recovery(self):
        """Check if we need to recover from a crash"""
        try:
            backup_path = self.base_path / "backups" / "last_state.json"
            if backup_path.exists():
                with open(backup_path, 'r') as f:
                    backup_data = json.load(f)
                # Check if the backup is newer than our current state
                current_state = self.base_path / "graph.json"
                if not current_state.exists() or backup_path.stat().st_mtime > current_state.stat().st_mtime:
                    logger.warning("Found newer backup data. Recovering from backup.")
                    # Perform recovery
                    backup_graph = self.base_path / "backups" / "graph.json"
                    if backup_graph.exists():
                        os.replace(backup_graph, self.base_path / "graph.json")
                        self.graph = MemoryGraph(self.base_path)  # Reload graph
        except Exception as e:
            logger.error(f"Error during recovery check: {e}")

    def create_backup(self, force: bool = False):
        """Create a backup of the current state with rotation and time-based limiting"""
        try:
            current_time = time.time()
            
            # Check if we need to create a backup based on time interval
            if not force and current_time - self.memory_stats['last_backup_time'] < self.memory_limits['backup_interval']:
                logger.debug("Backup skipped, not enough time elapsed since last backup")
                return False
                
            backup_dir = self.base_path / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            # Create timestamped backup directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_timestamp_dir = backup_dir / timestamp
            backup_timestamp_dir.mkdir(exist_ok=True)
            
            # Copy graph.json to timestamped backup directory
            graph_file = self.base_path / "graph.json"
            if graph_file.exists():
                backup_graph = backup_timestamp_dir / "graph.json"
                shutil.copy2(graph_file, backup_graph)
            
            # Backup vector index
            vector_dir = self.base_path / "vector_index"
            if vector_dir.exists():
                backup_vector = backup_timestamp_dir / "vector_index"
                backup_vector.mkdir(exist_ok=True)
                for file in vector_dir.glob("*"):
                    if file.is_file():
                        shutil.copy2(file, backup_vector / file.name)
            
            # Save state metadata
            state = {
                "timestamp": current_time,
                "backup_date": datetime.now().isoformat(),
                "num_nodes": len(self.graph.graph.nodes),
                "num_edges": len(self.graph.graph.edges),
                "memory_stats": self.memory_stats
            }
            with open(backup_timestamp_dir / "state.json", 'w') as f:
                json.dump(state, f, indent=2)
            
            # Also save to last_state.json for quick recovery
            with open(backup_dir / "last_state.json", 'w') as f:
                json.dump(state, f, indent=2)
                
            # Update backup time
            self.memory_stats['last_backup_time'] = current_time
            
            # Rotate old backups - keep only the most recent N backups
            backup_dirs = sorted([d for d in backup_dir.glob("*") if d.is_dir() and d.name[0].isdigit()], 
                               key=lambda d: d.stat().st_mtime, reverse=True)
                               
            if len(backup_dirs) > self.memory_limits['max_backups']:
                for old_dir in backup_dirs[self.memory_limits['max_backups']:]:
                    shutil.rmtree(old_dir)
                    logger.info(f"Removed old backup: {old_dir}")
                
            logger.info(f"Created backup with {state['num_nodes']} nodes in {backup_timestamp_dir}")
            return True
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return False
            
    def _cleanup_temp_files(self):
        """Clean up old temporary files"""
        try:
            temp_dir = self.base_path / "temp"
            if temp_dir.exists():
                # Delete files older than 7 days
                cutoff = time.time() - (7 * 86400)
                for file in temp_dir.glob("*"):
                    if file.is_file() and file.stat().st_mtime < cutoff:
                        file.unlink()
                        logger.debug(f"Deleted old temp file: {file}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
            
    def _load_command_history(self):
        """Load command history from previous sessions"""
        try:
            history_file = self.base_path / "state" / "command_history.json"
            if history_file.exists():
                with open(history_file, 'r') as f:
                    self.command_history = json.load(f)
                logger.info(f"Loaded command history with {len(self.command_history)} entries")
        except Exception as e:
            logger.error(f"Error loading command history: {e}")
            self.command_history = []
            
    def search_memory(self, query: str, limit: int = 10, category_id: Optional[str] = None,
                    tags: List[str] = None, types: List[str] = None, recency_boost: bool = True) -> List[dict]:
        """
        Search memory using vector similarity and keyword matching with advanced filtering
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            category_id: Filter by category ID
            tags: Filter by tags (ANY match)
            types: Filter by node types (e.g., 'document', 'conversation')
            recency_boost: Apply recency boost to newer documents
            
        Returns:
            List of matching memory nodes
        """
        try:
            # Update search stats
            self.memory_stats['searches_performed'] += 1
            
            # First try vector search
            vector_results = []
            if self.vector_index.model is not None:
                # Get top matches from vector index
                matches = self.vector_index.search(query, k=min(limit*3, 50))  # Get more to filter later
                for node_id, score in matches:
                    node = self.graph.graph.nodes.get(node_id)
                    if node:
                        # Apply filters
                        if category_id and node.get('category_id') != category_id:
                            continue
                        if tags and not any(tag in node.get('tags', []) for tag in tags):
                            continue
                        if types and node.get('type') not in types:
                            continue
                            
                        # Apply recency boost if enabled
                        if recency_boost:
                            # Calculate recency boost - newer documents get lower scores (better)
                            created_time = node.get('created_at', 0)
                            if isinstance(created_time, float) or isinstance(created_time, int):
                                age_days = max(0, (time.time() - created_time) / (24 * 3600))
                                # Log decay function for recency
                                recency_factor = 1.0 + min(2.0, 0.2 * math.log1p(age_days))
                                score = score * recency_factor
                        
                        # Add result with vector score
                        node_copy = node.copy()
                        node_copy['vector_score'] = score
                        vector_results.append(node_copy)
            
            # Also do keyword search
            keyword_matches = []
            for node_id in self.graph.graph.nodes:
                node = self.graph.graph.nodes[node_id]
                
                # Apply filters
                if category_id and node.get('category_id') != category_id:
                    continue
                if tags and not any(tag in node.get('tags', []) for tag in tags):
                    continue
                if types and node.get('type') not in types:
                    continue
                
                # Check for keyword match in title or content
                found = False
                title = node.get('title', '').lower()
                content = node.get('content', '').lower()
                query_parts = query.lower().split()
                
                # Priority 1: Exact phrase match
                if query.lower() in title or query.lower() in content:
                    found = True
                    match_quality = 1.0  # Highest quality
                
                # Priority 2: All words match (any order)
                elif all(part in title or part in content for part in query_parts):
                    found = True
                    match_quality = 0.8
                    
                # Priority 3: Most words match (at least 60%)
                elif len(query_parts) >= 3 and sum(1 for part in query_parts if part in title or part in content) >= len(query_parts) * 0.6:
                    found = True
                    match_quality = 0.5
                
                if found:
                    node_copy = node.copy()
                    # Add keyword match info and update access time
                    node_copy['keyword_match'] = True
                    node_copy['match_quality'] = match_quality
                    current_time = time.time()
                    self.graph.graph.nodes[node_id]['last_accessed'] = current_time
                    
                    # Store last search that found this node
                    if 'metadata' not in node_copy:
                        node_copy['metadata'] = {}
                    if 'search_history' not in node_copy['metadata']:
                        node_copy['metadata']['search_history'] = []
                    
                    # Add to search history (limited to last 5)
                    search_history = node_copy['metadata'].get('search_history', [])
                    search_history.append({
                        'query': query,
                        'timestamp': current_time,
                        'matched_by': 'keyword'
                    })
                    node_copy['metadata']['search_history'] = search_history[-5:]  # Keep last 5
                    
                    # Save updated metadata
                    self.graph.update_node(node_id, metadata=node_copy['metadata'])
                    keyword_matches.append(node_copy)
            
            # Combine results (prioritize keyword matches)
            keyword_ids = {n['id'] for n in keyword_matches}
            combined = keyword_matches + [n for n in vector_results if n['id'] not in keyword_ids]
            
            # Sort results by quality metrics
            # First sort keyword matches by match quality and recency
            keyword_matches.sort(key=lambda x: (-x.get('match_quality', 0), -x.get('last_accessed', 0)))
            # Then sort vector matches by score
            vector_results.sort(key=lambda x: x.get('vector_score', float('inf')))
            
            # Produce final combined and sorted list
            final_results = []
            # First add all keyword matches (already sorted)
            final_results.extend(keyword_matches)
            # Then add vector matches not already included
            for node in vector_results:
                if node['id'] not in {r['id'] for r in final_results}:
                    final_results.append(node)
                    
            # For each result, update the node with search metadata
            for result in final_results[:limit]:
                node_id = result['id']
                if node_id in self.graph.graph:
                    # Update access time
                    self.graph.graph.nodes[node_id]['last_accessed'] = time.time()
                    
                    # Record search hit in metadata
                    metadata = self.graph.graph.nodes[node_id].get('metadata', {})
                    search_hits = metadata.get('search_hits', 0) + 1
                    metadata['search_hits'] = search_hits
                    metadata['last_matched_query'] = query
                    self.graph.update_node(node_id, metadata=metadata)
            
            # Log search statistics
            logger.debug(f"Memory search: '{query}' found {len(final_results)} results " +
                        f"(keyword: {len(keyword_matches)}, vector: {len(vector_results)})")
                    
            # Return limited results
            return final_results[:limit]
            
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            # Fallback to basic search if something goes wrong
            matches = []
            try:
                for node_id in self.graph.graph.nodes:
                    node = self.graph.graph.nodes[node_id]
                    if category_id and node.get('category_id') != category_id:
                        continue
                    if tags and not any(tag in node.get('tags', []) for tag in tags):
                        continue
                    if types and node.get('type') not in types:
                        continue
                    if (query.lower() in node.get('title','').lower()
                        or query.lower() in node.get('content','').lower()):
                        matches.append(node)
                matches.sort(key=lambda x: x.get('last_accessed', 0), reverse=True)
                return matches[:limit]
            except:
                # Absolute fallback if even the backup search fails
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
