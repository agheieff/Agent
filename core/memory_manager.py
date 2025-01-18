import json
import os
from pathlib import Path
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(self, base_path="memory"):
        self.base_path = Path(base_path)
        self.conversations_path = self.base_path / "conversations"
        self.docs_path = self.base_path / "docs"
        self.context_path = self.base_path / "context"
        self.metrics_path = self.base_path / "metrics"
        self.tasks_path = self.base_path / "tasks"
        
        # Ensure all directories exist
        for path in [self.conversations_path, self.docs_path, 
                    self.context_path, self.metrics_path, self.tasks_path]:
            path.mkdir(parents=True, exist_ok=True)

    def load_conversation(self, conversation_id: str) -> List[Dict]:
        """Load a conversation from disk by its ID"""
        file_path = self.conversations_path / f"{conversation_id}.json"
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return data
        except json.JSONDecodeError:
            logger.error(f"Error decoding conversation file: {file_path}")
            return []
        except Exception as e:
            logger.error(f"Error loading conversation: {e}", exc_info=True)
            return []

    def save_conversation(self, conversation_id: str, messages: List[Dict]) -> bool:
        """Save a conversation to disk. Returns True if successful."""
        file_path = self.conversations_path / f"{conversation_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(messages, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving conversation: {e}", exc_info=True)
            return False

    def create_conversation(self) -> str:
        """Create a new conversation and return its ID"""
        conversation_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        metadata = {
            "id": conversation_id,
            "created_at": timestamp,
            "last_updated": timestamp
        }
        
        # Save metadata
        try:
            meta_path = self.conversations_path / f"{conversation_id}_meta.json"
            with open(meta_path, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving conversation metadata: {e}", exc_info=True)
        
        return conversation_id

    def save_document(self, name: str, content: str, 
                     metadata: Optional[Dict] = None) -> bool:
        """Save a document with optional metadata"""
        try:
            # Save content
            content_path = self.docs_path / f"{name}.txt"
            with open(content_path, 'w') as f:
                f.write(content)

            # Save metadata if provided
            if metadata:
                metadata_path = self.docs_path / f"{name}_meta.json"
                with open(metadata_path, 'w') as f:
                    json.dump(metadata, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving document: {e}", exc_info=True)
            return False

    def load_document(self, name: str) -> Optional[str]:
        """Load a document from the docs directory"""
        file_path = self.docs_path / f"{name}.txt"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading document: {e}", exc_info=True)
            return None
