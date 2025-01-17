# core/memory_manager.py

import json
import os
from pathlib import Path
import uuid

class MemoryManager:
    def __init__(self, base_path="memory"):
        self.base_path = Path(base_path)
        self.conversations_path = self.base_path / "conversations"
        self.docs_path = self.base_path / "docs"
        
        # Ensure directories exist
        self.conversations_path.mkdir(parents=True, exist_ok=True)
        self.docs_path.mkdir(parents=True, exist_ok=True)

    def load_conversation(self, conversation_id):
        """Load a conversation from disk by its ID"""
        file_path = self.conversations_path / f"{conversation_id}.json"
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error decoding conversation file: {file_path}")
            return []
        except Exception as e:
            print(f"Error loading conversation: {e}")
            return []

    def save_conversation(self, conversation_id, messages):
        """Save a conversation to disk"""
        file_path = self.conversations_path / f"{conversation_id}.json"
        try:
            with open(file_path, 'w') as f:
                json.dump(messages, f, indent=2)
        except Exception as e:
            print(f"Error saving conversation: {e}")

    def create_conversation(self):
        """Create a new conversation and return its ID"""
        return str(uuid.uuid4())

    def save_document(self, name, content):
        """Save a document to the docs directory"""
        file_path = self.docs_path / f"{name}.txt"
        try:
            with open(file_path, 'w') as f:
                f.write(content)
        except Exception as e:
            print(f"Error saving document: {e}")

    def load_document(self, name):
        """Load a document from the docs directory"""
        file_path = self.docs_path / f"{name}.txt"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error loading document: {e}")
            return None
