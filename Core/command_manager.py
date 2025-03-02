import logging
import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


class CommandManager:
    """
    Manages a collection of executed/planned commands.
    Can load/save them to disk, allowing consistent usage across sessions.
    """

    def __init__(self, storage_path: Path):
        """
        Args:
            storage_path: Base directory where commands.json or related
                          data can be saved/loaded.
        """
        self.storage_path = storage_path
        self.commands_file = self.storage_path / "commands.json"
        self.commands: List[Dict[str, Any]] = []
        self._load_commands()

    def _load_commands(self) -> None:
        """Load existing commands from disk if present."""
        try:
            if self.commands_file.exists():
                with open(self.commands_file, 'r', encoding='utf-8') as f:
                    self.commands = json.load(f)
                logger.info(f"Loaded {len(self.commands)} commands from {self.commands_file}")
            else:
                logger.debug(f"No commands file found at {self.commands_file}, starting empty.")
        except Exception as e:
            logger.error(f"Error loading commands: {e}")
            self.commands = []

    def _save_commands(self) -> None:
        """Persist all commands to disk."""
        try:
            self.commands_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.commands_file, 'w', encoding='utf-8') as f:
                json.dump(self.commands, f, indent=2)
            logger.debug(f"Saved {len(self.commands)} commands to {self.commands_file}")
        except Exception as e:
            logger.error(f"Error saving commands: {e}")

    def add_command(self, command: str, shell_type: str = "bash", success: bool = True, metadata: Optional[Dict] = None) -> None:
        """
        Add a new command record to the list.  
        Args:
            command: The actual command text or script.
            shell_type: Type of shell or environment (bash, python, etc.).
            success: Whether the command execution was successful.
            metadata: Arbitrary dict of extra info (timestamps, reasons, etc.).
        """
        if metadata is None:
            metadata = {}
        cmd_entry = {
            "id": f"cmd_{int(time.time())}_{uuid.uuid4().hex[:8]}",
            "command": command,
            "shell_type": shell_type,
            "success": success,
            "metadata": metadata,
            "timestamp": time.time()
        }
        self.commands.append(cmd_entry)
        logger.info(f"Added command: {command} (shell={shell_type}, success={success})")
        self._save_commands()

    def get_all_commands(self) -> List[Dict[str, Any]]:
        """Return the entire list of recorded commands in memory."""
        return self.commands

    def find_commands(self, query: str) -> List[Dict[str, Any]]:
        """
        Simple substring search in the 'command' field.  
        Returns all commands whose text contains 'query'.
        """
        query_lower = query.lower()
        return [cmd for cmd in self.commands if query_lower in cmd['command'].lower()]

    def remove_command(self, cmd_id: str) -> bool:
        """
        Remove a command by its ID.  
        Returns True if removed, False if not found.
        """
        for i, cmd in enumerate(self.commands):
            if cmd.get('id') == cmd_id:
                removed_cmd = self.commands.pop(i)
                logger.info(f"Removed command: {removed_cmd['command']}")
                self._save_commands()
                return True
        return False

    def clear_all_commands(self) -> None:
        """Wipe out all known commands (be careful)."""
        logger.warning("Clearing all commands from memory and disk!")
        self.commands = []
        self._save_commands()
