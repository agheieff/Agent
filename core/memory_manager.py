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
    """Handles preloading of relevant memory context with enhanced prioritization"""
    def __init__(self, memory_manager: 'MemoryManager'):
        self.memory_manager = memory_manager
        self.context_keys = [
            "system_config", "tool_usage", "error_history", "active_projects", 
            "agent_notes", "status_updates", "command_skills", "knowledge_base"
        ]
        
    def initialize_session(self):
        """Initialize the session by preloading essential memory items"""
        # Record session start in memory
        self.memory_manager.add_agent_note(
            "New session initialized. Loading context and knowledge.",
            note_type="session_management",
            importance="normal"
        )
        
        # Load mind maps if they're not already loaded
        self.memory_manager._load_mind_maps()
        
        # Ensure working memory state is available
        self._create_transition_record()
    
    def _create_transition_record(self):
        """Create a record of context transitions between sessions"""
        try:
            transitions_file = self.memory_manager.base_path / "context_transitions.json"
            transition_data = {
                "timestamp": time.time(),
                "agent_notes_count": len(self.memory_manager.search_memory("agent_notes", limit=100)),
                "knowledge_items_count": len(self.memory_manager.search_memory("knowledge_base", limit=100)),
                "mind_maps_count": len(self.memory_manager.mind_maps)
            }
            
            existing_transitions = []
            if transitions_file.exists():
                try:
                    with open(transitions_file, 'r') as f:
                        existing_transitions = json.load(f)
                except:
                    existing_transitions = []
            
            # Keep only the last 10 transitions
            existing_transitions.append(transition_data)
            if len(existing_transitions) > 10:
                existing_transitions = existing_transitions[-10:]
                
            with open(transitions_file, 'w') as f:
                json.dump(existing_transitions, f, indent=2)
        except Exception as e:
            logger.error(f"Error creating transition record: {e}")

    def get_session_context(self) -> str:
        """
        Get a comprehensive session context by intelligently prioritizing
        the most relevant memory items for the current session
        """
        context = []
        
        # Add a note about conversation length risk
        context.append("## Memory Management")
        context.append("IMPORTANT: As this conversation gets longer, there's an increasing risk of context loss.")
        context.append("Use the /compact command when needed to compress conversation history.")
        context.append("For complex tasks, break them into smaller sub-tasks to avoid memory limitations.")
        context.append("You can create mind maps for complex topics with memory_manager.create_mind_map().")
        context.append("Track important information with memory_manager.add_agent_note().")
        
        # Add mind maps first - they're high-level context and most valuable
        active_mind_maps = self._get_active_mind_maps(limit=2)
        if active_mind_maps:
            context.append("\n## Active Mind Maps")
            for mind_map in active_mind_maps:
                # Get a summarized version of the mind map
                map_summary = self.memory_manager.extract_mind_map_summary(mind_map["id"])
                # Only use a truncated version to save context space
                context.append(map_summary.split("\n\n")[0])  # Just include the header section
                # Add key concepts
                concept_section = "\nKey concepts:"
                nodes = list(self.memory_manager.mind_maps[mind_map["id"]]["nodes"].values())
                # Sort by importance (root node first, then by creation date)
                nodes.sort(key=lambda n: (n["type"] != "root", n.get("created_at", 0)))
                # Include only the first 5 nodes
                for node in nodes[:5]:
                    concept_section += f"\n- {node['title']}"
                context.append(concept_section)
        
        # Add agent notes and status first as they're highest priority
        for priority_key in ["agent_notes", "status_updates", "error_history"]:
            results = self.memory_manager.search_memory(priority_key, limit=5, recency_boost=True)
            if results:
                context.append(f"\n## {priority_key.replace('_', ' ').title()}")
                for n in results[:5]:
                    # Format the content nicely
                    note_content = n['content'].strip().replace("\n\n", "\n")
                    context.append(f"- {note_content}")
        
        # Add knowledge base items (high value, permanent memory)
        knowledge_items = self.memory_manager.search_memory(
            "knowledge_base", 
            tags=["knowledge_base", "permanent"],
            limit=3
        )
        if knowledge_items:
            context.append("\n## Knowledge Base")
            for item in knowledge_items:
                # Truncate content to save space
                content = item.get('content', '').strip()
                if len(content) > 200:
                    content = content[:197] + "..."
                context.append(f"- **{item.get('title', '')}**: {content}")
        
        # Add secondary context based on relevance scoring
        # We prioritize context based on recency and access patterns
        secondary_context = []
        for key in self.context_keys:
            if key not in ["agent_notes", "status_updates", "error_history", "knowledge_base"]:
                results = self.memory_manager.search_memory(key, limit=3, recency_boost=True)
                if results:
                    section = f"\n## {key.replace('_', ' ').title()}\n"
                    for n in results[:3]:
                        # Format the content nicely
                        content = n['content'].strip().replace("\n\n", "\n")
                        section += f"- {content}\n"
                    secondary_context.append((section, self._calculate_context_priority(key)))
        
        # Sort secondary context by priority score
        secondary_context.sort(key=lambda x: x[1], reverse=True)
        
        # Add the top 3 secondary contexts
        for section, _ in secondary_context[:3]:
            context.append(section)
        
        return "\n".join(context)
    
    def _get_active_mind_maps(self, limit: int = 2) -> List[Dict]:
        """Get the most recently active mind maps"""
        try:
            if not self.memory_manager.mind_maps:
                return []
                
            # Sort mind maps by last modified time
            sorted_maps = sorted(
                self.memory_manager.mind_maps.values(),
                key=lambda m: m.get("last_modified", 0),
                reverse=True
            )
            
            return [{"id": m["id"], "title": m["title"]} for m in sorted_maps[:limit]]
        except Exception as e:
            logger.error(f"Error getting active mind maps: {e}")
            return []
    
    def _calculate_context_priority(self, context_key: str) -> float:
        """Calculate a priority score for each context section"""
        # Base priorities
        base_priorities = {
            "command_skills": 0.8,
            "system_config": 0.6,
            "tool_usage": 0.7,
            "active_projects": 0.9,
        }
        
        # Add dynamic adjustment based on access patterns
        # If this context has been accessed frequently, boost its priority
        boost = 0.0
        if hasattr(self.memory_manager, 'memory_stats'):
            if context_key in self.memory_manager.memory_stats.get('access_patterns', {}):
                access_count = self.memory_manager.memory_stats['access_patterns'][context_key]
                boost = min(0.2, access_count * 0.02)  # Max boost of 0.2
                
        return base_priorities.get(context_key, 0.5) + boost

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
    
    # Define common context keys
    context_keys = [
        "system_config", "tool_usage", "error_history", "active_projects", 
        "agent_notes", "status_updates", "command_skills", "knowledge_base", 
        "important", "task", "mind_map", "code", "project"
    ]
    
    def __init__(self, base_path: Path = None):
        # If no path provided, use the configuration from memory.config file
        if base_path is None:
            base_path = self._get_configured_path()
        
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize conversation tracking
        self.conversation_turn_count = 0
        self.conversation_start_time = time.time()
        
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
                  'tasks', 'reflections', 'notes', 'working_memory', 'archive', 'mind_maps']:
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
            'searches_performed': 0,
            'mind_maps_created': 0,
            'notes_added': 0,
            'compressions_performed': 0,
            'access_patterns': {},  # Track which context types are accessed most frequently
            'retrieval_counts': {},  # Track which memory items are retrieved most often
            'query_patterns': [],   # Store recent search patterns
            'last_session_info': {
                'timestamp': time.time(),
                'duration_minutes': 0,
                'turn_count': 0,
                'tasks_completed': 0
            }
        }
        
        # Initialize memory indexing limits
        self.memory_limits = {
            'max_document_size': 1024 * 1024,  # 1MB
            'max_indexed_entries': 10000,
            'max_backups': 10, 
            'backup_interval': 3600  # 1 hour
        }
        
        # Initialize mind map structure
        self.mind_maps = {}
        self._load_mind_maps()
        
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
        """Check if we need to recover from a crash and restore memory state"""
        try:
            backup_path = self.base_path / "backups" / "last_state.json"
            if backup_path.exists():
                with open(backup_path, 'r') as f:
                    backup_data = json.load(f)
                # Check if the backup is newer than our current state
                current_state = self.base_path / "graph.json"
                if not current_state.exists() or backup_path.stat().st_mtime > current_state.stat().st_mtime:
                    logger.warning("Found newer backup data. Recovering from backup.")
                    
                    # Get the most recent backup directory
                    backup_dirs = sorted([d for d in (self.base_path / "backups").glob("*") 
                                         if d.is_dir() and d.name[0].isdigit()], 
                                      key=lambda d: d.stat().st_mtime, reverse=True)
                    
                    if backup_dirs:
                        recent_backup = backup_dirs[0]
                        logger.info(f"Using most recent backup from {recent_backup}")
                        
                        # Perform graph recovery
                        backup_graph = recent_backup / "graph.json"
                        if backup_graph.exists():
                            os.replace(backup_graph, self.base_path / "graph.json")
                            self.graph = MemoryGraph(self.base_path)  # Reload graph
                        
                        # Recover mind maps
                        mind_maps_dir = recent_backup / "mind_maps"
                        if mind_maps_dir.exists() and mind_maps_dir.is_dir():
                            for map_file in mind_maps_dir.glob("*.json"):
                                try:
                                    with open(map_file, 'r') as f:
                                        mind_map = json.load(f)
                                        map_id = map_file.stem
                                        self.mind_maps[map_id] = mind_map
                                        
                                    # Also save to main mind_maps directory
                                    dest_dir = self.base_path / "mind_maps"
                                    dest_dir.mkdir(exist_ok=True)
                                    shutil.copy2(map_file, dest_dir / map_file.name)
                                except Exception as e:
                                    logger.error(f"Error recovering mind map {map_file}: {e}")
                        
                        # Recover memory stats
                        stats_dir = recent_backup / "stats"
                        if stats_dir.exists() and stats_dir.is_dir():
                            # Recover access patterns
                            access_file = stats_dir / "access_patterns.json"
                            if access_file.exists():
                                try:
                                    with open(access_file, 'r') as f:
                                        self.memory_stats['access_patterns'] = json.load(f)
                                except Exception as e:
                                    logger.error(f"Error recovering access patterns: {e}")
                            
                            # Recover retrieval counts
                            retrieval_file = stats_dir / "retrieval_counts.json"
                            if retrieval_file.exists():
                                try:
                                    with open(retrieval_file, 'r') as f:
                                        self.memory_stats['retrieval_counts'] = json.load(f)
                                except Exception as e:
                                    logger.error(f"Error recovering retrieval counts: {e}")
                            
                            # Recover query patterns
                            query_file = stats_dir / "query_patterns.json"
                            if query_file.exists():
                                try:
                                    with open(query_file, 'r') as f:
                                        self.memory_stats['query_patterns'] = json.load(f)
                                except Exception as e:
                                    logger.error(f"Error recovering query patterns: {e}")
                            
                            # Recover conversation metrics
                            metrics_file = stats_dir / "conversation_metrics.json"
                            if metrics_file.exists():
                                try:
                                    with open(metrics_file, 'r') as f:
                                        metrics = json.load(f)
                                        # Store as last session info
                                        self.memory_stats['last_session_info'] = {
                                            'timestamp': metrics.get('timestamp', 0),
                                            'duration_minutes': metrics.get('duration', 0) / 60,
                                            'turn_count': metrics.get('turn_count', 0),
                                            'tasks_completed': 0  # Can't recover this easily
                                        }
                                except Exception as e:
                                    logger.error(f"Error recovering conversation metrics: {e}")
                    
                    # Log successful recovery
                    logger.info("Recovery complete. Memory state restored.")
                    
                    # Create an agent note about the recovery
                    try:
                        self.add_agent_note(
                            "Memory state recovered from backup. Previous session information restored.",
                            note_type="system_event",
                            importance="normal",
                            tags=["recovery", "system"]
                        )
                    except Exception as note_error:
                        logger.error(f"Error creating recovery note: {note_error}")
        except Exception as e:
            logger.error(f"Error during recovery check: {e}")

    def create_backup(self, force: bool = False):
        """
        Create a backup of the current state with rotation and time-based limiting.
        Enhanced with memory stats preservation for continuity.
        """
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
            
            # Backup mind maps
            if hasattr(self, 'mind_maps') and self.mind_maps:
                mind_maps_dir = backup_timestamp_dir / "mind_maps"
                mind_maps_dir.mkdir(exist_ok=True)
                
                # Save each mind map
                for map_id, mind_map in self.mind_maps.items():
                    with open(mind_maps_dir / f"{map_id}.json", 'w') as f:
                        json.dump(mind_map, f, indent=2)
            
            # Save access patterns to preserve learning across restarts
            stats_dir = backup_timestamp_dir / "stats"
            stats_dir.mkdir(exist_ok=True)
            
            # Save access patterns
            access_patterns_file = stats_dir / "access_patterns.json"
            with open(access_patterns_file, 'w') as f:
                json.dump(self.memory_stats.get('access_patterns', {}), f, indent=2)
            
            # Save retrieval counts (limited to top 100 to avoid bloat)
            retrieval_counts = self.memory_stats.get('retrieval_counts', {})
            top_items = sorted(retrieval_counts.items(), key=lambda x: x[1], reverse=True)[:100]
            with open(stats_dir / "retrieval_counts.json", 'w') as f:
                json.dump(dict(top_items), f, indent=2)
            
            # Save query patterns
            with open(stats_dir / "query_patterns.json", 'w') as f:
                json.dump(self.memory_stats.get('query_patterns', []), f, indent=2)
            
            # Save conversation metrics
            with open(stats_dir / "conversation_metrics.json", 'w') as f:
                json.dump({
                    "turn_count": self.conversation_turn_count,
                    "duration": time.time() - self.conversation_start_time,
                    "timestamp": time.time()
                }, f, indent=2)
            
            # Save state metadata
            state = {
                "timestamp": current_time,
                "backup_date": datetime.now().isoformat(),
                "num_nodes": len(self.graph.graph.nodes),
                "num_edges": len(self.graph.graph.edges),
                "conversation_turn_count": self.conversation_turn_count,
                "conversation_duration": time.time() - self.conversation_start_time,
                "memory_stats": {
                    key: value for key, value in self.memory_stats.items() 
                    if key not in ['access_patterns', 'retrieval_counts', 'query_patterns']
                }
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
                
            logger.info(f"Created enhanced backup with {state['num_nodes']} nodes and memory stats preservation in {backup_timestamp_dir}")
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
            search_start_time = time.time()
            self.memory_stats['searches_performed'] += 1
            
            # Track search patterns
            # Record which context types are being searched for
            if tags:
                for tag in tags:
                    if tag in self.context_keys:
                        # Update access count for this context type
                        self.memory_stats['access_patterns'][tag] = self.memory_stats['access_patterns'].get(tag, 0) + 1
            
            # Keep track of recent queries (limited to last 20)
            self.memory_stats['query_patterns'].append({
                'query': query,
                'timestamp': time.time(),
                'tags': tags,
                'types': types
            })
            if len(self.memory_stats['query_patterns']) > 20:
                self.memory_stats['query_patterns'] = self.memory_stats['query_patterns'][-20:]
            
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
                                
                            # Add access frequency boost - frequently accessed items get priority
                            if 'metadata' in node and 'search_hits' in node['metadata']:
                                access_count = node['metadata']['search_hits']
                                # Logarithmic boost to prevent domination by very frequent items
                                access_boost = max(0, 0.2 * math.log1p(access_count))
                                # Apply boost (lower score is better for retrieval)
                                score = score / (1.0 + access_boost)
                        
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
                    
                    # Track retrieval counts for memory items in global stats
                    self.memory_stats['retrieval_counts'][node_id] = self.memory_stats['retrieval_counts'].get(node_id, 0) + 1
                    
                    # If we're retrieving an item with tags, boost those context types
                    item_tags = node.get('tags', [])
                    for tag in item_tags:
                        if tag in self.context_keys:
                            self.memory_stats['access_patterns'][tag] = self.memory_stats['access_patterns'].get(tag, 0) + 1
            
            # Log search statistics
            search_time = time.time() - search_start_time
            logger.debug(f"Memory search: '{query}' found {len(final_results)} results in {search_time:.3f}s " +
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
            
    def add_agent_note(self, note: str, note_type: str = "general", importance: str = "normal", tags: List[str] = None):
        """
        Add a short note about the agent's current activity or system state.
        These notes are high-priority memory items that persist across sessions.
        
        Args:
            note: Content of the note
            note_type: Type of note (activity, error, decision, etc.)
            importance: Importance level (high, normal, low)
            tags: Additional tags for categorization
        
        Returns:
            ID of the saved note
        """
        # Ensure note is concise
        if len(note) > 500:
            note = note[:497] + "..."
            
        # Create standard tags
        note_tags = ["agent_notes", note_type]
        if tags:
            note_tags.extend(tags)
        if importance == "high":
            note_tags.append("important")
            
        # Generate title based on note type and timestamp
        title = f"{note_type.title()} Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        # Set permanence based on importance
        permanent = (importance == "high")
        
        # Save the note
        node_id = self.save_document(
            title=title,
            content=note,
            tags=note_tags,
            metadata={
                "note_type": note_type,
                "importance": importance,
                "conversation_turn": self.conversation_turn_count
            },
            permanent=permanent
        )
        
        logger.info(f"Added agent note: {note[:50]}{'...' if len(note) > 50 else ''}")
        return node_id
        
    def update_conversation_metrics(self, increment_turns: bool = True):
        """
        Update conversation metrics to track length and duration.
        Call this method at each conversation turn.
        
        Args:
            increment_turns: Whether to increment the turn counter
        """
        if increment_turns:
            self.conversation_turn_count += 1
            
        # Calculate conversation duration
        current_time = time.time()
        duration_minutes = (current_time - self.conversation_start_time) / 60
        
        # Check if we should add warnings about conversation length
        if self.conversation_turn_count % 10 == 0 or (duration_minutes > 30 and self.conversation_turn_count % 5 == 0):
            risk_level = "low"
            if self.conversation_turn_count > 50 or duration_minutes > 60:
                risk_level = "high"
            elif self.conversation_turn_count > 30 or duration_minutes > 45:
                risk_level = "medium"
                
            # Add a status update about conversation length
            if risk_level != "low":
                self.add_agent_note(
                    f"Conversation length: {self.conversation_turn_count} turns over {duration_minutes:.1f} minutes. " +
                    f"Context window risk: {risk_level}. Consider using /compact command soon.",
                    note_type="status_update",
                    importance="high" if risk_level == "high" else "normal",
                    tags=["conversation_length", "status_updates", risk_level]
                )
                
        return {
            "turns": self.conversation_turn_count,
            "duration_minutes": duration_minutes
        }
        
    def log_task_status(self, task_title: str, status: str, details: str = None):
        """
        Log the status of a task in progress.
        
        Args:
            task_title: Title of the task
            status: Current status (started, in_progress, completed, error)
            details: Optional details about the status
        """
        status_note = f"Task: {task_title}\nStatus: {status}"
        if details:
            status_note += f"\nDetails: {details}"
            
        importance = "high" if status in ["completed", "error"] else "normal"
        
        self.add_agent_note(
            status_note,
            note_type="status_updates",
            importance=importance,
            tags=["task_status", status]
        )
        
    def _load_mind_maps(self):
        """Load existing mind maps from disk"""
        try:
            mind_maps_dir = self.base_path / "mind_maps"
            for map_file in mind_maps_dir.glob("*.json"):
                try:
                    with open(map_file, 'r') as f:
                        mind_map = json.load(f)
                        map_id = map_file.stem
                        self.mind_maps[map_id] = mind_map
                except Exception as e:
                    logger.error(f"Error loading mind map {map_file}: {e}")
        except Exception as e:
            logger.error(f"Error loading mind maps: {e}")
            
    def _save_mind_map(self, map_id: str):
        """Save a mind map to disk"""
        try:
            mind_maps_dir = self.base_path / "mind_maps"
            mind_maps_dir.mkdir(exist_ok=True)
            
            with open(mind_maps_dir / f"{map_id}.json", 'w') as f:
                json.dump(self.mind_maps[map_id], f, indent=2)
                
            logger.info(f"Saved mind map {map_id}")
        except Exception as e:
            logger.error(f"Error saving mind map {map_id}: {e}")
            
    def create_mind_map(self, title: str, description: str = "", map_type: str = "task") -> str:
        """
        Create a new mind map for organizing memory by concepts and relationships.
        
        Args:
            title: Title of the mind map
            description: Description of the mind map's purpose
            map_type: Type of mind map (task, project, concept, etc.)
            
        Returns:
            ID of the created mind map
        """
        map_id = f"map_{int(time.time())}_{hash(title) % 10000}"
        
        # Create basic mind map structure
        self.mind_maps[map_id] = {
            "id": map_id,
            "title": title,
            "description": description,
            "type": map_type,
            "created_at": time.time(),
            "last_modified": time.time(),
            "nodes": {},
            "links": [],
            "metadata": {
                "node_count": 0,
                "link_count": 0,
                "priority": "normal"
            }
        }
        
        # Add central/root node
        root_node_id = self._add_mind_map_node(
            map_id, 
            title,
            description, 
            node_type="root",
            position={"x": 0, "y": 0}
        )
        self.mind_maps[map_id]["root_node_id"] = root_node_id
        
        # Save to disk
        self._save_mind_map(map_id)
        
        # Update stats
        self.memory_stats['mind_maps_created'] += 1
        
        # Create a note about the mind map creation
        self.add_agent_note(
            f"Created new mind map: {title}",
            note_type="mind_map_created",
            importance="normal",
            tags=["mind_map", map_type]
        )
        
        return map_id
        
    def _add_mind_map_node(self, map_id: str, title: str, content: str, 
                           node_type: str = "concept", position: Dict = None,
                           metadata: Dict = None) -> str:
        """Add a node to a mind map"""
        if map_id not in self.mind_maps:
            raise ValueError(f"Mind map {map_id} does not exist")
            
        # Generate a unique node ID
        node_id = f"node_{int(time.time())}_{hash(title) % 10000}"
        
        # Set default position if not provided
        if position is None:
            position = {"x": 0, "y": 0}
            
        # Create the node
        self.mind_maps[map_id]["nodes"][node_id] = {
            "id": node_id,
            "title": title,
            "content": content,
            "type": node_type,
            "position": position,
            "created_at": time.time(),
            "last_accessed": time.time(),
            "metadata": metadata or {}
        }
        
        # Update node count
        self.mind_maps[map_id]["metadata"]["node_count"] += 1
        self.mind_maps[map_id]["last_modified"] = time.time()
        
        return node_id
        
    def add_mind_map_concept(self, map_id: str, title: str, content: str, 
                            related_to: str = None, link_type: str = "related",
                            position: Dict = None) -> str:
        """
        Add a concept to a mind map and optionally link it to another node.
        
        Args:
            map_id: ID of the mind map
            title: Title of the concept
            content: Content/description of the concept
            related_to: Optional ID of a node to link to
            link_type: Type of relationship
            position: Optional position {x, y} coordinates
            
        Returns:
            ID of the created node
        """
        # Add the node
        node_id = self._add_mind_map_node(
            map_id,
            title,
            content,
            node_type="concept",
            position=position
        )
        
        # Create link if related_to is provided
        if related_to and related_to in self.mind_maps[map_id]["nodes"]:
            self._add_mind_map_link(map_id, related_to, node_id, link_type)
            
        # Save changes
        self._save_mind_map(map_id)
        
        return node_id
        
    def _add_mind_map_link(self, map_id: str, source_id: str, target_id: str, 
                         link_type: str = "related", strength: float = 1.0):
        """Add a link between two nodes in a mind map"""
        if map_id not in self.mind_maps:
            raise ValueError(f"Mind map {map_id} does not exist")
            
        # Create the link
        link_id = f"link_{source_id}_{target_id}"
        
        # Check if link already exists
        for link in self.mind_maps[map_id]["links"]:
            if link["source"] == source_id and link["target"] == target_id:
                # Update existing link
                link["type"] = link_type
                link["strength"] = strength
                link["last_modified"] = time.time()
                return link_id
                
        # Add new link
        self.mind_maps[map_id]["links"].append({
            "id": link_id,
            "source": source_id,
            "target": target_id,
            "type": link_type,
            "strength": strength,
            "created_at": time.time(),
            "last_modified": time.time()
        })
        
        # Update link count
        self.mind_maps[map_id]["metadata"]["link_count"] += 1
        self.mind_maps[map_id]["last_modified"] = time.time()
        
        return link_id
        
    def get_mind_map(self, map_id: str) -> Dict:
        """Get a mind map by ID"""
        if map_id not in self.mind_maps:
            raise ValueError(f"Mind map {map_id} does not exist")
            
        # Update access time
        for node_id in self.mind_maps[map_id]["nodes"]:
            self.mind_maps[map_id]["nodes"][node_id]["last_accessed"] = time.time()
            
        return self.mind_maps[map_id]
        
    def search_mind_maps(self, query: str, limit: int = 3) -> List[Dict]:
        """
        Search for relevant mind maps based on title, description, and content.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching mind maps
        """
        results = []
        query_lower = query.lower()
        
        for map_id, mind_map in self.mind_maps.items():
            score = 0
            
            # Check title and description match
            if query_lower in mind_map["title"].lower():
                score += 10
            if query_lower in mind_map.get("description", "").lower():
                score += 5
                
            # Check node content match
            content_matches = 0
            for node_id, node in mind_map["nodes"].items():
                if query_lower in node["title"].lower():
                    score += 3
                    content_matches += 1
                if query_lower in node["content"].lower():
                    score += 2
                    content_matches += 1
                    
            # Bonus for multiple content matches
            score += min(content_matches, 5)
            
            # If there's any match, add to results
            if score > 0:
                results.append({
                    "id": map_id,
                    "title": mind_map["title"],
                    "description": mind_map.get("description", ""),
                    "node_count": mind_map["metadata"]["node_count"],
                    "score": score,
                    "created_at": mind_map["created_at"]
                })
                
        # Sort by score and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def extract_mind_map_summary(self, map_id: str) -> str:
        """
        Generate a text summary of a mind map for inclusion in context.
        
        Args:
            map_id: ID of the mind map
            
        Returns:
            Text summary of the mind map
        """
        if map_id not in self.mind_maps:
            return "Mind map not found"
            
        mind_map = self.mind_maps[map_id]
        
        # Build summary parts
        summary_parts = [
            f"# Mind Map: {mind_map['title']}",
            mind_map.get("description", "")
        ]
        
        # Add key concepts (nodes)
        summary_parts.append("\n## Key Concepts")
        
        # Sort nodes by type and creation time
        nodes = list(mind_map["nodes"].values())
        nodes.sort(key=lambda x: (x["type"] != "root", x["created_at"]))
        
        # Add nodes to summary
        for i, node in enumerate(nodes):
            if i < 10:  # Limit to 10 nodes to avoid overload
                summary_parts.append(f"- {node['title']}: {node['content'][:100]}{'...' if len(node['content']) > 100 else ''}")
        
        if len(nodes) > 10:
            summary_parts.append(f"...and {len(nodes) - 10} more concepts")
            
        # Generate a simple text representation of relationships
        if mind_map["links"]:
            summary_parts.append("\n## Relationships")
            link_count = min(len(mind_map["links"]), 7)  # Limit to 7 relationships
            
            for i in range(link_count):
                link = mind_map["links"][i]
                source_node = mind_map["nodes"].get(link["source"], {})
                target_node = mind_map["nodes"].get(link["target"], {})
                
                if source_node and target_node:
                    summary_parts.append(f"- {source_node.get('title', 'Unknown')} → {link['type']} → {target_node.get('title', 'Unknown')}")
                    
            if len(mind_map["links"]) > link_count:
                summary_parts.append(f"...and {len(mind_map['links']) - link_count} more relationships")
                
        return "\n".join(summary_parts)
        
    def get_session_persistent_memory(self) -> Dict[str, Any]:
        """
        Get the persistent memory data that should be shared across sessions.
        This provides continuity between different agent sessions.
        
        Returns:
            Dict containing persistent memory data
        """
        persistent_data = {
            "agent_notes": [],
            "task_statuses": [],
            "mind_maps": [],
            "important_files": [],
            "knowledge_base": []
        }
        
        # Get recent agent notes
        try:
            agent_notes = self.search_memory(
                "important", 
                tags=["agent_notes", "important"], 
                limit=10,
                recency_boost=True
            )
            
            for note in agent_notes:
                persistent_data["agent_notes"].append({
                    "content": note.get("content", ""),
                    "type": note.get("metadata", {}).get("note_type", "general"),
                    "timestamp": note.get("metadata", {}).get("timestamp", 0),
                    "importance": note.get("metadata", {}).get("importance", "normal")
                })
        except Exception as e:
            logger.error(f"Error loading agent notes for persistent memory: {e}")
        
        # Get recent task statuses
        try:
            task_statuses = self.search_memory(
                "task status", 
                tags=["task_status", "status_updates"], 
                limit=7,
                recency_boost=True
            )
            
            for status in task_statuses:
                persistent_data["task_statuses"].append({
                    "content": status.get("content", ""),
                    "timestamp": status.get("created_at", 0)
                })
        except Exception as e:
            logger.error(f"Error loading task statuses for persistent memory: {e}")
        
        # Get recent mind maps (limit to 2 most recent)
        try:
            if self.mind_maps:
                recent_maps = sorted(
                    self.mind_maps.values(),
                    key=lambda m: m.get("last_modified", 0),
                    reverse=True
                )[:2]
                
                for mind_map in recent_maps:
                    persistent_data["mind_maps"].append({
                        "id": mind_map.get("id"),
                        "title": mind_map.get("title"),
                        "description": mind_map.get("description", ""),
                        "nodes_count": mind_map.get("metadata", {}).get("node_count", 0),
                        "links_count": mind_map.get("metadata", {}).get("link_count", 0)
                    })
        except Exception as e:
            logger.error(f"Error loading mind maps for persistent memory: {e}")
        
        # Get general knowledge items
        try:
            knowledge_items = self.search_memory(
                "important knowledge", 
                tags=["knowledge_base", "permanent"], 
                limit=5,
                recency_boost=False  # Knowledge items don't need recency bias
            )
            
            for item in knowledge_items:
                persistent_data["knowledge_base"].append({
                    "title": item.get("title", ""),
                    "content": item.get("content", "")[:250] + ("..." if len(item.get("content", "")) > 250 else "")
                })
        except Exception as e:
            logger.error(f"Error loading knowledge items for persistent memory: {e}")
        
        return persistent_data
        
    def add_to_knowledge_base(self, title: str, content: str, tags: List[str] = None) -> str:
        """
        Add an item to the permanent knowledge base.
        Knowledge base items persist across sessions and are high priority items.
        
        Args:
            title: Title of the knowledge item
            content: Content of the knowledge item
            tags: Additional tags for categorization
            
        Returns:
            ID of the saved knowledge item
        """
        # Create standard tags
        kb_tags = ["knowledge_base", "permanent"]
        if tags:
            kb_tags.extend(tags)
        
        # Save the knowledge item
        node_id = self.save_document(
            title=title,
            content=content,
            tags=kb_tags,
            permanent=True,  # Knowledge base items are always permanent
            metadata={
                "type": "knowledge_base",
                "added_at": time.time(),
                "importance": "high"
            }
        )
        
        logger.info(f"Added knowledge base item: {title}")
        
        # Create a note about the addition
        self.add_agent_note(
            f"Added to knowledge base: {title}",
            note_type="knowledge_base",
            importance="high",
            tags=["knowledge_base"]
        )
        
        return node_id
        
    def prioritize_memory_items(self, query: str, items: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Prioritize memory items based on relevance to query and importance.
        
        Args:
            query: The search query or current context
            items: List of memory items to prioritize
            top_k: Number of top items to return
            
        Returns:
            List of prioritized items
        """
        if not items:
            return []
            
        scored_items = []
        query_terms = query.lower().split()
        
        for item in items:
            score = 0
            
            # Base score from metadata importance
            importance = item.get("metadata", {}).get("importance", "normal")
            if importance == "high":
                score += 10
            elif importance == "normal":
                score += 5
            
            # Score from relevance to query
            content = item.get("content", "").lower()
            title = item.get("title", "").lower()
            
            # Exact matches get higher score
            if query.lower() in content or query.lower() in title:
                score += 15
            
            # Term matches
            term_matches = sum(1 for term in query_terms if term in content or term in title)
            score += term_matches * 2
            
            # Recency bonus (logarithmic decay)
            timestamp = item.get("metadata", {}).get("timestamp", 0)
            if timestamp > 0:
                time_diff = time.time() - timestamp
                days_old = time_diff / (24 * 3600)
                # Newer items get higher scores
                recency_score = max(0, 5 - min(5, math.log(1 + days_old)))
                score += recency_score
            
            # Tags bonus
            tags = item.get("tags", [])
            if "important" in tags:
                score += 5
            if "permanent" in tags:
                score += 3
            
            scored_items.append((item, score))
        
        # Sort by score (descending)
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # Return top_k items
        return [item for item, _ in scored_items[:top_k]]
