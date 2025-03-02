import os
import re
import json
import logging
import glob
from pathlib import Path
from typing import List, Dict, Optional, Any, Set

logger = logging.getLogger(__name__)

class FileOperations:
    """
    Manages file operations for the agent. Enforces a "view before edit" policy
    to reduce accidental overwrites. 
    """

    def __init__(self):
        self.current_dir = os.getcwd()
        # Track which files have been viewed this session:
        self.viewed_files: Set[str] = set()

    def view(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """
        Read contents of a file from 'offset' lines, up to 'limit' lines.
        Marks the file as viewed so it can be safely edited or replaced.
        """
        try:
            abs_path = self._ensure_absolute_path(file_path)
            if not os.path.exists(abs_path):
                return f"Error: File not found: {abs_path}"
            if os.path.isdir(abs_path):
                return f"Error: {abs_path} is a directory"
            if self._is_image_file(abs_path):
                self.viewed_files.add(abs_path)
                return f"[Image file: {abs_path}]"
            if self._is_binary_file(abs_path):
                self.viewed_files.add(abs_path)
                return f"[Binary file: {abs_path}]"

            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                # Skip lines up to 'offset'
                for _ in range(offset):
                    next(f, None)

                lines = []
                for _ in range(limit):
                    line = next(f, None)
                    if line is None:
                        break
                    # Truncate overly long lines:
                    if len(line) > 2000:
                        line = line[:2000] + " [line truncated]\n"
                    lines.append(line)

                content = ''.join(lines)
                if len(lines) == limit and next(f, None) is not None:
                    content += "\n[...file content truncated...]\n"

            # Mark file as viewed
            self.viewed_files.add(abs_path)
            return content

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return f"Error reading file: {str(e)}"

    def edit(self, file_path: str, old_string: str, new_string: str) -> str:
        """
        Replaces ONE occurrence of 'old_string' with 'new_string'.
        The old_string must uniquely identify the specific instance to change.
        
        CRITICAL REQUIREMENTS:
        1. UNIQUENESS: The old_string MUST uniquely identify one specific instance.
           Include sufficient context (at least 3-5 lines) before and after the change point.
        2. SINGLE INSTANCE: This tool can only change ONE instance at a time.
           Make separate calls for each instance.
           
        To create a new file, use an empty old_string and supply the content in new_string.
        Requires that you have viewed the file first, unless it's newly created.
        """
        try:
            abs_path = self._ensure_absolute_path(file_path)
            # If file doesn't exist:
            if not os.path.exists(abs_path):
                # If old_string is specified, that implies we expected an existing file
                # If truly new, do a simple creation with new_string content:
                if old_string:
                    return f"Error: File not found: {abs_path}"
                else:
                    parent_dir = os.path.dirname(abs_path)
                    if parent_dir and not os.path.exists(parent_dir):
                        os.makedirs(parent_dir, exist_ok=True)
                    with open(abs_path, 'w', encoding='utf-8') as f:
                        f.write(new_string)
                    self.viewed_files.add(abs_path)
                    return f"Created new file: {abs_path}"

            # If file *does* exist but hasn't been viewed, warn but proceed:
            if abs_path not in self.viewed_files:
                logger.warning(f"Warning: Editing file that wasn't viewed: {abs_path}")

            with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            if old_string and old_string not in content:
                return f"Error: Target string not found in {abs_path}"
                
            # Check for uniqueness of the old_string
            if old_string:
                # Count occurrences by splitting and counting
                occurrences = content.count(old_string)
                if occurrences > 1:
                    return f"Error: The target string appears {occurrences} times in {abs_path}. It must uniquely identify a single instance. Include more context."
                elif occurrences == 0:
                    return f"Error: Target string not found in {abs_path}"
                    
                # Replace exactly one occurrence:
                new_content = content.replace(old_string, new_string, 1)
            else:
                # If old_string is empty, we create or overwrite the file:
                new_content = new_string

            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            self.viewed_files.add(abs_path)
            return f"Successfully edited file: {abs_path}"

        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            return f"Error editing file: {str(e)}"

    def replace(self, file_path: str, content: str) -> str:
        """
        Replaces the entire file content. 
        Must have viewed the file first if it exists, or explicitly intend to overwrite.
        """
        try:
            abs_path = self._ensure_absolute_path(file_path)
            # If file exists and not viewed, warn but proceed
            if os.path.exists(abs_path) and abs_path not in self.viewed_files:
                logger.warning(f"Warning: Replacing file not previously viewed: {abs_path}")

            parent_dir = os.path.dirname(abs_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)

            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(content)

            self.viewed_files.add(abs_path)
            return f"Updated file: {abs_path}"

        except Exception as e:
            logger.error(f"Error replacing file {file_path}: {e}")
            return f"Error replacing file: {str(e)}"

    def _ensure_absolute_path(self, path: str) -> str:
        """
        Converts a potentially relative path to an absolute path 
        based on the current_dir.
        """
        if not os.path.isabs(path):
            return os.path.abspath(os.path.join(self.current_dir, path))
        return path

    def _is_binary_file(self, file_path: str) -> bool:
        """
        Basic detection if a file is binary by reading its first chunk 
        and checking for null bytes.
        """
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(4096)
                return b'\0' in chunk
        except:
            return False

    def _is_image_file(self, file_path: str) -> bool:
        """
        Very basic extension-based image check.
        """
        return any(file_path.lower().endswith(ext) 
                   for ext in ['.jpg','.jpeg','.png','.gif','.bmp','.svg','.webp'])