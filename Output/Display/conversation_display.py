"""
Display manager for conversation interactions.
"""

import sys
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from Output.Config.config_manager import ConfigManager

class ConversationDisplay:
    """
    Manages the display of conversation between user and assistant.
    Ensures proper alternating of messages with visual indicators.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the conversation display manager.

        Args:
            config_path: Optional path to config file
        """
        self._config = ConfigManager(config_path)
        self._last_role = None  # Track the last role displayed
        self.colors = {
            "user": "\033[94m",  # Blue
            "assistant": "\033[92m",  # Green
            "system": "\033[93m",  # Yellow
            "error": "\033[91m",  # Red
            "reset": "\033[0m"  # Reset
        }

    def display_message(self, message: str, role: str = "assistant", 
                        force_new_line: bool = False, timestamp: bool = True):
        """
        Display a message with visual indicators based on role.

        Args:
            message: The message to display
            role: The role (user/assistant/system)
            force_new_line: Force display even if it's the same role as previous
            timestamp: Whether to show timestamp
        """
        # Check if this is duplicate role without forcing new line
        if role == self._last_role and not force_new_line:
            # Just continue the message
            print(message)
            return

        # Show role prefixes if configured
        show_roles = self._config.get("show_conversation_roles", True)
        use_colors = self._config.get("colors_enabled", True)

        # Set prefix based on role
        if show_roles:
            if role == "user":
                prefix = "User: "
            elif role == "assistant":
                prefix = "Assistant: "
            elif role == "system":
                prefix = "System: "
            else:
                prefix = f"{role.capitalize()}: "
        else:
            prefix = ""

        # Add timestamp if enabled
        time_prefix = ""
        if timestamp and self._config.get("show_timestamps", True):
            time_prefix = f"[{datetime.now().strftime('%H:%M:%S')}] "

        # Add color if enabled
        if use_colors and role in self.colors:
            prefix = f"{self.colors[role]}{time_prefix}{prefix}{self.colors['reset']}"
        else:
            prefix = f"{time_prefix}{prefix}"

        # Print with proper spacing
        print()  # Add extra line before new role
        print(f"{prefix}{message}")

        # Update last role
        self._last_role = role

    def display_alternating_conversation(self, messages: List[Dict[str, Any]]):
        """
        Display a conversation history with proper alternating formatting.

        Args:
            messages: List of message dictionaries with role/content
        """
        last_role = None

        for msg in messages:
            role = msg.get("role", "assistant")
            content = msg.get("content", "")

            # Force a new line between messages with the same role
            force_new_line = (role == last_role)

            self.display_message(content, role, force_new_line)
            last_role = role

    def display_typing_indicator(self, role: str = "assistant"):
        """
        Display a typing indicator (thinking animation).

        Args:
            role: The role that is typing
        """
        if self._config.get("show_conversation_roles", True):
            if role == "user":
                prefix = "User is typing"
            elif role == "assistant":
                prefix = "Assistant is thinking"
            else:
                prefix = f"{role.capitalize()} is typing"
        else:
            prefix = "Thinking"

        # Add color if enabled
        if self._config.get("colors_enabled", True) and role in self.colors:
            prefix = f"{self.colors[role]}{prefix}{self.colors['reset']}"

        # Print animated dots
        sys.stdout.write(f"\r{prefix}...")
        sys.stdout.flush()

    def clear_typing_indicator(self):
        """Clear the typing indicator animation."""
        sys.stdout.write("\r" + " " * 50 + "\r")
        sys.stdout.flush()

    def display_input_prompt(self):
        """Display the user input prompt."""
        if self._config.get("show_conversation_roles", True):
            prompt = "User: "
            if self._config.get("colors_enabled", True):
                prompt = f"{self.colors['user']}{prompt}{self.colors['reset']}"
        else:
            prompt = "> "

        print("\n" + prompt, end="", flush=True)
        self._last_role = "user"  # Set last role to user

    def reset_conversation(self):
        """Reset the conversation display state."""
        self._last_role = None