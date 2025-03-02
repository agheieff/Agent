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
from .command_manager import CommandManager  # <-- now actually used

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
        self.memory_manager.add_agent_note(
            "New session initialized. Loading context and knowledge.",
            note_type="session_management",
            importance="normal"
        )
        self.memory_manager._load_mind_maps()
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
            
            existing_transitions.append(transition_data)
            if len(existing_transitions) > 10:
                existing_transitions = existing_transitions[-10:]
                
            with open(transitions_file, 'w') as f:
                json.dump(existing_transitions, f, indent=2)
        except Exception as e:
            logger.error(f"Error creating transition record: {e}")

    def get_session_context(self) -> str:
        """
        Build a string of session context from memory. 
        This example method is optional and purely illustrative.
        """
        context = []
        context.append("## Memory Management")
        context.append("IMPORTANT: If the conversation grows too large, use /compact to reduce memory usage.")
        context.append("Use mind maps for complex tasks with memory_manager.create_mind_map().")
        
        active_mind_maps = self._get_active_mind_maps(limit=2)
        if active_mind_maps:
            context.append("\n## Active Mind Maps")
            for mm in active_mind_maps:
                map_summary = self.memory_manager.extract_mind_map_summary(mm["id"])
                context.append(map_summary.split("\n\n")[0])
        
        for priority_key in ["agent_notes", "status_updates", "error_history"]:
            results = self.memory_manager.search_memory(priority_key, limit=5, recency_boost=True)
            if results:
                context.append(f"\n## {priority_key.title()}")
                for r in results:
                    content = r.get('content', '').replace("\n\n", "\n")
                    context.append(f"- {content}")
        
        knowledge_items = self.memory_manager.search_memory(
            "knowledge_base", tags=["knowledge_base", "permanent"], limit=3
        )
        if knowledge_items:
            context.append("\n## Knowledge Base")
            for item in knowledge_items:
                c = item.get('content', '')[:200]
                context.append(f"- **{item.get('title', '')}**: {c}...")
        
        return "\n".join(context)
    
    def _get_active_mind_maps(self, limit: int = 2) -> List[Dict]:
        if not self.memory_manager.mind_maps:
            return []
        sorted_maps = sorted(
            self.memory_manager.mind_maps.values(),
            key=lambda m: m.get("last_modified", 0),
            reverse=True
        )
        return [{"id": m["id"], "title": m["title"]} for m in sorted_maps[:limit]]


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

class MemoryManager:
    """High-level memory manager that composes a MemoryGraph + MemoryHierarchy + TemporalContext + VectorIndex"""
    
    context_keys = [
        "system_config", "tool_usage", "error_history", "active_projects", 
        "agent_notes", "status_updates", "command_skills", "knowledge_base", 
        "important", "task", "mind_map", "code", "project"
    ]
    
    def __init__(self, base_path: Path = None):
        if base_path is None:
            base_path = self._get_configured_path()
        
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize conversation tracking
        self.conversation_turn_count = 0
        self.conversation_start_time = time.time()
        
        # Save the configured path
        self._save_configured_path(self.base_path)
        
        # Create the memory graph, hierarchy, temporal context, vector index
        self.graph = MemoryGraph(self.base_path)
        self.hierarchy = MemoryHierarchy(self.base_path)
        self.temporal = TemporalContext(self.graph)
        self.vector_index = VectorIndex(self.base_path)
        
        # Initialize the CommandManager
        self.command_manager = CommandManager(self.base_path / "commands")
        
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
            'access_patterns': {},
            'retrieval_counts': {},
            'query_patterns': [],
            'last_session_info': {
                'timestamp': time.time(),
                'duration_minutes': 0,
                'turn_count': 0,
                'tasks_completed': 0
            }
        }
        self.memory_limits = {
            'max_document_size': 1024 * 1024,
            'max_indexed_entries': 10000,
            'max_backups': 10,
            'backup_interval': 3600
        }
        self.mind_maps = {}
        self._load_mind_maps()
        self._load_command_history()
        self._check_for_recovery()
        self._cleanup_temp_files()
        
    def _get_configured_path(self) -> Path:
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
        memory_dir = os.environ.get("AGENT_MEMORY_DIR")
        if memory_dir:
            return Path(memory_dir)
        agent_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for path_option in [agent_dir.parent / "AgentMemory", Path.cwd() / "memory", Path.cwd() / "AgentMemory"]:
            if path_option.exists() or path_option.parent.exists():
                return path_option
        return agent_dir / "memory"
        
    def _save_configured_path(self, path: Path):
        try:
            agent_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = agent_dir / "memory.config"
            with open(config_path, 'w') as f:
                f.write(str(path))
        except Exception as e:
            logger.error(f"Error saving memory configuration: {e}")
        for d in ['documents','conversations','vector_index','temporal','commands','backups',
                  'tasks','reflections','notes','working_memory','archive','mind_maps']:
            (self.base_path / d).mkdir(exist_ok=True)
    
    def save_document(self, title: str, content: str,
                      tags: List[str] = None,
                      metadata: Dict = None,
                      category_id: Optional[str] = None,
                      permanent: bool = False) -> str:
        try:
            if len(content) > self.memory_limits['max_document_size']:
                original_size = len(content)
                content = content[:self.memory_limits['max_document_size']] + "\n...[CONTENT TRUNCATED]"
                logger.warning(f"Document '{title}' truncated from {original_size} to {len(content)} bytes")
                if metadata is None:
                    metadata = {}
                metadata['truncated'] = True
                metadata['original_size'] = original_size
            if permanent:
                if metadata is None:
                    metadata = {}
                metadata['permanent'] = True
            if metadata is None:
                metadata = {}
            timestamp = time.time()
            metadata['timestamp'] = timestamp
            metadata['created_at'] = datetime.now().isoformat()
            node_id = self.graph.add_node(
                title=title,
                content=content,
                type='document',
                tags=tags or [],
                metadata=metadata,
                category_id=category_id
            )
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
            self.vector_index.add_text(node_id, f"{title}\n{content}")
            self.memory_stats['nodes_added'] += 1
            self.memory_stats['documents_saved'] += 1
            if (self.memory_stats['nodes_added'] % 10 == 0 or permanent
                or 'important' in (tags or [])):
                self.create_backup()
            return node_id
        except Exception as e:
            logger.error(f"Error saving document: {e}")
            return ""
            
    def save_conversation(self, conversation_id: str, messages: List[Dict],
                          metadata: Dict = None, category_id: Optional[str] = None) -> str:
        try:
            summary = self._summarize_conversation(messages)
            content = json.dumps(messages, indent=2)
            node_id = self.graph.add_node(
                title=f"Conversation {conversation_id}",
                content=content,
                type='conversation',
                metadata={**(metadata or {}), 'summary': summary},
                category_id=category_id
            )
            conv_path = self.base_path / "conversations" / f"{conversation_id}.json"
            with open(conv_path, 'w') as f:
                json.dump({
                    'messages': messages,
                    'metadata': {**(metadata or {}), 'summary': summary},
                    'category_id': category_id,
                    'created_at': datetime.now().isoformat()
                }, f, indent=2)
            self.vector_index.add_text(node_id, summary)
            if len(self.graph.graph.nodes) % 10 == 0:
                self.create_backup()
            return node_id
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            return ""
            
    def _summarize_conversation(self, messages: List[Dict]) -> str:
        try:
            user_msgs = [m['content'] for m in messages if m.get('role') == 'user']
            assistant_msgs = [m['content'] for m in messages if m.get('role') == 'assistant']
            summary_parts = []
            if user_msgs:
                summary_parts.append("User asked about: " + "; ".join(user_msgs[:3]))
            if assistant_msgs:
                if len(assistant_msgs) >= 2:
                    summary_parts.append("Assistant initially responded: " + assistant_msgs[0][:200])
                    summary_parts.append("Assistant concluded with: " + assistant_msgs[-1][:200])
                elif len(assistant_msgs) == 1:
                    summary_parts.append("Assistant responded: " + assistant_msgs[0][:300])
            commands = []
            command_pattern = r"<(bash|python)>(.*?)</\1>"
            for msg in assistant_msgs:
                matches = re.finditer(command_pattern, msg, re.DOTALL)
                for match in matches:
                    cmd_type, cmd_text = match.groups()
                    commands.append(f"{cmd_type}: {cmd_text.strip()}")
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
        try:
            backup_path = self.base_path / "backups" / "last_state.json"
            if backup_path.exists():
                with open(backup_path, 'r') as f:
                    backup_data = json.load(f)
                current_state = self.base_path / "graph.json"
                if (not current_state.exists()
                    or backup_path.stat().st_mtime > current_state.stat().st_mtime):
                    logger.warning("Found newer backup data. Recovering from backup.")
                    backup_dirs = sorted([d for d in (self.base_path / "backups").glob("*")
                                         if d.is_dir() and d.name[0].isdigit()],
                                         key=lambda d: d.stat().st_mtime, reverse=True)
                    if backup_dirs:
                        recent_backup = backup_dirs[0]
                        logger.info(f"Using most recent backup from {recent_backup}")
                        backup_graph = recent_backup / "graph.json"
                        if backup_graph.exists():
                            os.replace(backup_graph, self.base_path / "graph.json")
                            self.graph = MemoryGraph(self.base_path)
                        mind_maps_dir = recent_backup / "mind_maps"
                        if mind_maps_dir.exists() and mind_maps_dir.is_dir():
                            for map_file in mind_maps_dir.glob("*.json"):
                                try:
                                    with open(map_file, 'r') as f:
                                        mind_map = json.load(f)
                                        map_id = map_file.stem
                                        self.mind_maps[map_id] = mind_map
                                    dest_dir = self.base_path / "mind_maps"
                                    dest_dir.mkdir(exist_ok=True)
                                    shutil.copy2(map_file, dest_dir / map_file.name)
                                except Exception as e:
                                    logger.error(f"Error recovering mind map {map_file}: {e}")
                        stats_dir = recent_backup / "stats"
                        if stats_dir.exists() and stats_dir.is_dir():
                            access_file = stats_dir / "access_patterns.json"
                            if access_file.exists():
                                try:
                                    with open(access_file, 'r') as f:
                                        self.memory_stats['access_patterns'] = json.load(f)
                                except Exception as e:
                                    logger.error(f"Error recovering access patterns: {e}")
                            retrieval_file = stats_dir / "retrieval_counts.json"
                            if retrieval_file.exists():
                                try:
                                    with open(retrieval_file, 'r') as f:
                                        self.memory_stats['retrieval_counts'] = json.load(f)
                                except Exception as e:
                                    logger.error(f"Error recovering retrieval counts: {e}")
                            query_file = stats_dir / "query_patterns.json"
                            if query_file.exists():
                                try:
                                    with open(query_file, 'r') as f:
                                        self.memory_stats['query_patterns'] = json.load(f)
                                except Exception as e:
                                    logger.error(f"Error recovering query patterns: {e}")
                            metrics_file = stats_dir / "conversation_metrics.json"
                            if metrics_file.exists():
                                try:
                                    with open(metrics_file, 'r') as f:
                                        metrics = json.load(f)
                                        self.memory_stats['last_session_info'] = {
                                            'timestamp': metrics.get('timestamp', 0),
                                            'duration_minutes': metrics.get('duration', 0)/60,
                                            'turn_count': metrics.get('turn_count', 0),
                                            'tasks_completed': 0
                                        }
                                except Exception as e:
                                    logger.error(f"Error recovering conversation metrics: {e}")
                    logger.info("Recovery complete. Memory state restored.")
                    try:
                        self.add_agent_note(
                            "Memory state recovered from backup. Previous session info restored.",
                            note_type="system_event",
                            importance="normal",
                            tags=["recovery", "system"]
                        )
                    except Exception as e:
                        logger.error(f"Error creating recovery note: {e}")
        except Exception as e:
            logger.error(f"Error during recovery check: {e}")
            
    def create_backup(self, force: bool = False):
        try:
            current_time = time.time()
            if not force and current_time - self.memory_stats['last_backup_time'] < self.memory_limits['backup_interval']:
                logger.debug("Backup skipped, not enough time elapsed since last backup")
                return False
            backup_dir = self.base_path / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_timestamp_dir = backup_dir / timestamp
            backup_timestamp_dir.mkdir(exist_ok=True)
            graph_file = self.base_path / "graph.json"
            if graph_file.exists():
                backup_graph = backup_timestamp_dir / "graph.json"
                shutil.copy2(graph_file, backup_graph)
            vector_dir = self.base_path / "vector_index"
            if vector_dir.exists():
                backup_vector = backup_timestamp_dir / "vector_index"
                backup_vector.mkdir(exist_ok=True)
                for file in vector_dir.glob("*"):
                    if file.is_file():
                        shutil.copy2(file, backup_vector / file.name)
            if hasattr(self, 'mind_maps') and self.mind_maps:
                mind_maps_dir = backup_timestamp_dir / "mind_maps"
                mind_maps_dir.mkdir(exist_ok=True)
                for map_id, mind_map in self.mind_maps.items():
                    with open(mind_maps_dir / f"{map_id}.json", 'w') as f:
                        json.dump(mind_map, f, indent=2)
            stats_dir = backup_timestamp_dir / "stats"
            stats_dir.mkdir(exist_ok=True)
            access_patterns_file = stats_dir / "access_patterns.json"
            with open(access_patterns_file, 'w') as f:
                json.dump(self.memory_stats.get('access_patterns', {}), f, indent=2)
            retrieval_counts = self.memory_stats.get('retrieval_counts', {})
            top_items = sorted(retrieval_counts.items(), key=lambda x: x[1], reverse=True)[:100]
            with open(stats_dir / "retrieval_counts.json", 'w') as f:
                json.dump(dict(top_items), f, indent=2)
            with open(stats_dir / "query_patterns.json", 'w') as f:
                json.dump(self.memory_stats.get('query_patterns', []), f, indent=2)
            with open(stats_dir / "conversation_metrics.json", 'w') as f:
                json.dump({
                    "turn_count": self.conversation_turn_count,
                    "duration": time.time() - self.conversation_start_time,
                    "timestamp": time.time()
                }, f, indent=2)
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
            with open(backup_dir / "last_state.json", 'w') as f:
                json.dump(state, f, indent=2)
            self.memory_stats['last_backup_time'] = current_time
            backup_dirs = sorted([d for d in backup_dir.glob("*") if d.is_dir() and d.name[0].isdigit()],
                                 key=lambda d: d.stat().st_mtime, reverse=True)
            if len(backup_dirs) > self.memory_limits['max_backups']:
                for old_dir in backup_dirs[self.memory_limits['max_backups']:]:
                    shutil.rmtree(old_dir)
                    logger.info(f"Removed old backup: {old_dir}")
            logger.info(f"Created enhanced backup with {state['num_nodes']} nodes in {backup_timestamp_dir}")
            return True
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return False
            
    def _cleanup_temp_files(self):
        try:
            temp_dir = self.base_path / "temp"
            if temp_dir.exists():
                cutoff = time.time() - (7 * 86400)
                for file in temp_dir.glob("*"):
                    if file.is_file() and file.stat().st_mtime < cutoff:
                        file.unlink()
                        logger.debug(f"Deleted old temp file: {file}")
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")
            
    def _load_command_history(self):
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
        try:
            search_start_time = time.time()
            self.memory_stats['searches_performed'] += 1
            if tags:
                for tag in tags:
                    if tag in self.context_keys:
                        self.memory_stats['access_patterns'][tag] = self.memory_stats['access_patterns'].get(tag, 0) + 1
            self.memory_stats['query_patterns'].append({
                'query': query,
                'timestamp': time.time(),
                'tags': tags,
                'types': types
            })
            if len(self.memory_stats['query_patterns']) > 20:
                self.memory_stats['query_patterns'] = self.memory_stats['query_patterns'][-20:]
            vector_results = []
            if self.vector_index.model is not None:
                matches = self.vector_index.search(query, k=min(limit*3, 50))
                for node_id, score in matches:
                    node = self.graph.graph.nodes.get(node_id)
                    if node:
                        if category_id and node.get('category_id') != category_id:
                            continue
                        if tags and not any(tag in node.get('tags', []) for tag in tags):
                            continue
                        if types and node.get('type') not in types:
                            continue
                        if recency_boost:
                            created_time = node.get('created_at', 0)
                            if isinstance(created_time, (float, int)):
                                age_days = max(0, (time.time() - created_time)/(24*3600))
                                recency_factor = 1.0 + min(2.0, 0.2*math.log1p(age_days))
                                score = score * recency_factor
                            if 'metadata' in node and 'search_hits' in node['metadata']:
                                access_count = node['metadata']['search_hits']
                                access_boost = max(0, 0.2*math.log1p(access_count))
                                score = score / (1.0 + access_boost)
                        node_copy = node.copy()
                        node_copy['vector_score'] = score
                        vector_results.append(node_copy)
            keyword_matches = []
            for node_id in self.graph.graph.nodes:
                node = self.graph.graph.nodes[node_id]
                if category_id and node.get('category_id') != category_id:
                    continue
                if tags and not any(tag in node.get('tags', []) for tag in tags):
                    continue
                if types and node.get('type') not in types:
                    continue
                found = False
                title = node.get('title', '').lower()
                content = node.get('content', '').lower()
                query_parts = query.lower().split()
                if query.lower() in title or query.lower() in content:
                    found = True
                    match_quality = 1.0
                elif all(part in title or part in content for part in query_parts):
                    found = True
                    match_quality = 0.8
                elif (len(query_parts)>=3 and sum(1 for p in query_parts if p in title or p in content)>=len(query_parts)*0.6):
                    found = True
                    match_quality = 0.5
                if found:
                    node_copy = node.copy()
                    node_copy['keyword_match'] = True
                    node_copy['match_quality'] = match_quality
                    current_time = time.time()
                    self.graph.graph.nodes[node_id]['last_accessed'] = current_time
                    if 'metadata' not in node_copy:
                        node_copy['metadata'] = {}
                    if 'search_history' not in node_copy['metadata']:
                        node_copy['metadata']['search_history'] = []
                    search_history = node_copy['metadata'].get('search_history', [])
                    search_history.append({
                        'query': query,
                        'timestamp': current_time,
                        'matched_by': 'keyword'
                    })
                    node_copy['metadata']['search_history'] = search_history[-5:]
                    self.graph.update_node(node_id, metadata=node_copy['metadata'])
                    keyword_matches.append(node_copy)
            keyword_ids = {km['id'] for km in keyword_matches}
            combined = keyword_matches + [v for v in vector_results if v['id'] not in keyword_ids]
            keyword_matches.sort(key=lambda x: (-x.get('match_quality', 0), -x.get('last_accessed', 0)))
            vector_results.sort(key=lambda x: x.get('vector_score', float('inf')))
            final_results = []
            final_results.extend(keyword_matches)
            for node in vector_results:
                if node['id'] not in {r['id'] for r in final_results}:
                    final_results.append(node)
            for result in final_results[:limit]:
                node_id = result['id']
                if node_id in self.graph.graph:
                    self.graph.graph.nodes[node_id]['last_accessed'] = time.time()
                    metadata = self.graph.graph.nodes[node_id].get('metadata', {})
                    search_hits = metadata.get('search_hits', 0) + 1
                    metadata['search_hits'] = search_hits
                    metadata['last_matched_query'] = query
                    self.graph.update_node(node_id, metadata=metadata)
                    self.memory_stats['retrieval_counts'][node_id] = self.memory_stats['retrieval_counts'].get(node_id, 0) + 1
                    item_tags = result.get('tags', [])
                    for tag in item_tags:
                        if tag in self.context_keys:
                            self.memory_stats['access_patterns'][tag] = self.memory_stats['access_patterns'].get(tag, 0) + 1
            search_time = time.time() - search_start_time
            logger.debug(f"Memory search: '{query}' got {len(final_results)} results in {search_time:.3f}s")
            return final_results[:limit]
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
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
                    if query.lower() in node.get('title','').lower() or query.lower() in node.get('content','').lower():
                        matches.append(node)
                matches.sort(key=lambda x: x.get('last_accessed', 0), reverse=True)
                return matches[:limit]
            except:
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
            return [c.name for c in categories]
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
        if len(self.command_history) > 1000:
            self.command_history = self.command_history[-1000:]
        
        # Also store commands in CommandManager
        self.command_manager.add_command(command, shell_type=shell, success=success)

    def add_agent_note(self, note: str, note_type: str = "general", importance: str = "normal", tags: List[str] = None):
        if len(note) > 500:
            note = note[:497] + "..."
        note_tags = ["agent_notes", note_type]
        if tags:
            note_tags.extend(tags)
        if importance == "high":
            note_tags.append("important")
        title = f"{note_type.title()} Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        node_id = self.save_document(
            title=title,
            content=note,
            tags=note_tags,
            metadata={
                "note_type": note_type,
                "importance": importance,
                "conversation_turn": self.conversation_turn_count
            },
            permanent=(importance=="high")
        )
        logger.info(f"Added agent note: {note[:50]}{'...' if len(note) > 50 else ''}")
        return node_id
        
    def update_conversation_metrics(self, increment_turns: bool = True) -> Dict[str, Any]:
        if increment_turns:
            self.conversation_turn_count += 1
        current_time = time.time()
        duration_minutes = (current_time - self.conversation_start_time) / 60
        if self.conversation_turn_count % 10 == 0 or (duration_minutes > 30 and self.conversation_turn_count % 5 == 0):
            risk_level = "low"
            if self.conversation_turn_count > 50 or duration_minutes > 60:
                risk_level = "high"
            elif self.conversation_turn_count > 30 or duration_minutes > 45:
                risk_level = "medium"
            if risk_level != "low":
                self.add_agent_note(
                    f"Conversation length: {self.conversation_turn_count} turns over {duration_minutes:.1f} minutes. Risk: {risk_level}. Consider using /compact soon.",
                    note_type="status_update",
                    importance="high" if risk_level=="high" else "normal",
                    tags=["conversation_length", "status_updates", risk_level]
                )
        return {
            "turns": self.conversation_turn_count,
            "duration_minutes": duration_minutes
        }
        
    def log_task_status(self, task_title: str, status: str, details: str = None):
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
        try:
            mind_maps_dir = self.base_path / "mind_maps"
            mind_maps_dir.mkdir(exist_ok=True)
            with open(mind_maps_dir / f"{map_id}.json", 'w') as f:
                json.dump(self.mind_maps[map_id], f, indent=2)
            logger.info(f"Saved mind map {map_id}")
        except Exception as e:
            logger.error(f"Error saving mind map {map_id}: {e}")
            
    def create_mind_map(self, title: str, description: str = "", map_type: str = "task") -> str:
        map_id = f"map_{int(time.time())}_{hash(title)%10000}"
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
        root_node_id = self._add_mind_map_node(
            map_id, 
            title,
            description, 
            node_type="root",
            position={"x": 0, "y": 0}
        )
        self.mind_maps[map_id]["root_node_id"] = root_node_id
        self._save_mind_map(map_id)
        self.memory_stats['mind_maps_created'] += 1
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
        if map_id not in self.mind_maps:
            raise ValueError(f"Mind map {map_id} does not exist")
        node_id = f"node_{int(time.time())}_{hash(title)%10000}"
        if position is None:
            position = {"x": 0, "y": 0}
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
        self.mind_maps[map_id]["metadata"]["node_count"] += 1
        self.mind_maps[map_id]["last_modified"] = time.time()
        return node_id
        
    def add_mind_map_concept(self, map_id: str, title: str, content: str, 
                            related_to: str = None, link_type: str = "related",
                            position: Dict = None) -> str:
        node_id = self._add_mind_map_node(
            map_id,
            title,
            content,
            node_type="concept",
            position=position
        )
        if related_to and related_to in self.mind_maps[map_id]["nodes"]:
            self._add_mind_map_link(map_id, related_to, node_id, link_type)
        self._save_mind_map(map_id)
        return node_id
        
    def _add_mind_map_link(self, map_id: str, source_id: str, target_id: str, 
                         link_type: str = "related", strength: float = 1.0):
        if map_id not in self.mind_maps:
            raise ValueError(f"Mind map {map_id} does not exist")
        link_id = f"link_{source_id}_{target_id}"
        for link in self.mind_maps[map_id]["links"]:
            if link["source"] == source_id and link["target"] == target_id:
                link["type"] = link_type
                link["strength"] = strength
                link["last_modified"] = time.time()
                return link_id
        self.mind_maps[map_id]["links"].append({
            "id": link_id,
            "source": source_id,
            "target": target_id,
            "type": link_type,
            "strength": strength,
            "created_at": time.time(),
            "last_modified": time.time()
        })
        self.mind_maps[map_id]["metadata"]["link_count"] += 1
        self.mind_maps[map_id]["last_modified"] = time.time()
        return link_id
        
    def get_mind_map(self, map_id: str) -> Dict:
        if map_id not in self.mind_maps:
            raise ValueError(f"Mind map {map_id} does not exist")
        for node_id in self.mind_maps[map_id]["nodes"]:
            self.mind_maps[map_id]["nodes"][node_id]["last_accessed"] = time.time()
        return self.mind_maps[map_id]
        
    def search_mind_maps(self, query: str, limit: int = 3) -> List[Dict]:
        results = []
        query_lower = query.lower()
        for map_id, mm in self.mind_maps.items():
            score = 0
            if query_lower in mm["title"].lower():
                score += 10
            if query_lower in mm.get("description", "").lower():
                score += 5
            content_matches = 0
            for node_id, node in mm["nodes"].items():
                if query_lower in node["title"].lower():
                    score += 3
                    content_matches += 1
                if query_lower in node["content"].lower():
                    score += 2
                    content_matches += 1
            score += min(content_matches, 5)
            if score > 0:
                results.append({
                    "id": map_id,
                    "title": mm["title"],
                    "description": mm.get("description", ""),
                    "node_count": mm["metadata"]["node_count"],
                    "score": score,
                    "created_at": mm["created_at"]
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def extract_mind_map_summary(self, map_id: str) -> str:
        if map_id not in self.mind_maps:
            return "Mind map not found"
        mm = self.mind_maps[map_id]
        summary_parts = [
            f"# Mind Map: {mm['title']}",
            mm.get("description", "")
        ]
        summary_parts.append("\n## Key Concepts")
        nodes = list(mm["nodes"].values())
        nodes.sort(key=lambda x: (x["type"] != "root", x["created_at"]))
        for i, node in enumerate(nodes):
            if i < 10:
                snippet = node["content"][:100]
                if len(node["content"]) > 100:
                    snippet += "..."
                summary_parts.append(f"- {node['title']}: {snippet}")
        if len(nodes) > 10:
            summary_parts.append(f"...and {len(nodes) - 10} more concepts")
        if mm["links"]:
            summary_parts.append("\n## Relationships")
            link_count = min(len(mm["links"]), 7)
            for i in range(link_count):
                link = mm["links"][i]
                source = mm["nodes"].get(link["source"], {})
                target = mm["nodes"].get(link["target"], {})
                if source and target:
                    summary_parts.append(f"- {source.get('title', '?')} → {link['type']} → {target.get('title', '?')}")
            if len(mm["links"]) > link_count:
                summary_parts.append(f"...and {len(mm['links']) - link_count} more relationships")
        return "\n".join(summary_parts)
        
    def get_session_persistent_memory(self) -> Dict[str, Any]:
        persistent_data = {
            "agent_notes": [],
            "task_statuses": [],
            "mind_maps": [],
            "important_files": [],
            "knowledge_base": []
        }
        try:
            agent_notes = self.search_memory("important", tags=["agent_notes", "important"], limit=10, recency_boost=True)
            for note in agent_notes:
                persistent_data["agent_notes"].append({
                    "content": note.get("content", ""),
                    "type": note.get("metadata", {}).get("note_type", "general"),
                    "timestamp": note.get("metadata", {}).get("timestamp", 0),
                    "importance": note.get("metadata", {}).get("importance", "normal")
                })
        except Exception as e:
            logger.error(f"Error loading agent notes for persistent memory: {e}")
        
        try:
            task_statuses = self.search_memory("task status", tags=["task_status", "status_updates"], limit=7, recency_boost=True)
            for status in task_statuses:
                persistent_data["task_statuses"].append({
                    "content": status.get("content", ""),
                    "timestamp": status.get("created_at", 0)
                })
        except Exception as e:
            logger.error(f"Error loading task statuses for persistent memory: {e}")
        
        try:
            if self.mind_maps:
                recent_maps = sorted(
                    self.mind_maps.values(),
                    key=lambda m: m.get("last_modified", 0),
                    reverse=True
                )[:2]
                for mm in recent_maps:
                    persistent_data["mind_maps"].append({
                        "id": mm.get("id"),
                        "title": mm.get("title"),
                        "description": mm.get("description", ""),
                        "nodes_count": mm.get("metadata", {}).get("node_count", 0),
                        "links_count": mm.get("metadata", {}).get("link_count", 0)
                    })
        except Exception as e:
            logger.error(f"Error loading mind maps for persistent memory: {e}")
        
        try:
            knowledge_items = self.search_memory("important knowledge", tags=["knowledge_base", "permanent"], limit=5, recency_boost=False)
            for item in knowledge_items:
                content = item.get("content", "").strip()
                if len(content) > 250:
                    content = content[:247] + "..."
                persistent_data["knowledge_base"].append({
                    "title": item.get("title", ""),
                    "content": content
                })
        except Exception as e:
            logger.error(f"Error loading knowledge items for persistent memory: {e}")
        
        return persistent_data
        
    def add_to_knowledge_base(self, title: str, content: str, tags: List[str] = None) -> str:
        kb_tags = ["knowledge_base", "permanent"]
        if tags:
            kb_tags.extend(tags)
        node_id = self.save_document(
            title=title,
            content=content,
            tags=kb_tags,
            permanent=True,
            metadata={
                "type": "knowledge_base",
                "added_at": time.time(),
                "importance": "high"
            }
        )
        logger.info(f"Added knowledge base item: {title}")
        self.add_agent_note(
            f"Added to knowledge base: {title}",
            note_type="knowledge_base",
            importance="high",
            tags=["knowledge_base"]
        )
        return node_id
        
    def prioritize_memory_items(self, query: str, items: List[Dict], top_k: int = 5) -> List[Dict]:
        if not items:
            return []
        scored_items = []
        query_terms = query.lower().split()
        for item in items:
            score = 0
            importance = item.get("metadata", {}).get("importance", "normal")
            if importance == "high":
                score += 10
            elif importance == "normal":
                score += 5
            content = item.get("content", "").lower()
            title = item.get("title", "").lower()
            if query.lower() in content or query.lower() in title:
                score += 15
            term_matches = sum(1 for term in query_terms if term in content or term in title)
            score += term_matches * 2
            timestamp = item.get("metadata", {}).get("timestamp", 0)
            if timestamp > 0:
                time_diff = time.time() - timestamp
                days_old = time_diff / (24 * 3600)
                recency_score = max(0, 5 - min(5, math.log1p(days_old)))
                score += recency_score
            tags = item.get("tags", [])
            if "important" in tags:
                score += 5
            if "permanent" in tags:
                score += 3
            scored_items.append((item, score))
        scored_items.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in scored_items[:top_k]]
