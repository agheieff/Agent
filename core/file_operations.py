import os
import re
import logging
import glob
from pathlib import Path
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class FileOperations:
    """
    Provides file operation capabilities similar to Claude Code functions:
    - View: Read file contents
    - Edit: Modify specific parts of files
    - Replace: Completely replace file contents
    - GlobTool: Find files matching a pattern
    - GrepTool: Search for content within files
    - LS: List directory contents
    """
    
    def __init__(self):
        self.current_dir = os.getcwd()
    
    def view(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """
        Read a file from the filesystem with optional offset and limit.
        
        Args:
            file_path: Absolute path to the file to read
            offset: The line number to start reading from (0-indexed)
            limit: The number of lines to read
            
        Returns:
            File contents as a string
        """
        try:
            # Convert to absolute path if it's not already
            file_path = self._ensure_absolute_path(file_path)
            
            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"
                
            if os.path.isdir(file_path):
                return f"Error: {file_path} is a directory, not a file"
                
            # Handle image files
            if self._is_image_file(file_path):
                return f"[Image file: {file_path}]"
                
            # Handle binary files
            if self._is_binary_file(file_path):
                return f"[Binary file: {file_path}]"
                
            # Read file with offset and limit
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                if offset > 0:
                    # Skip lines up to offset
                    for _ in range(offset):
                        next(f, None)
                
                # Read specified number of lines
                lines = []
                for _ in range(limit):
                    line = next(f, None)
                    if line is None:
                        break
                    
                    # Truncate long lines
                    if len(line) > 2000:
                        line = line[:2000] + " [line truncated]\n"
                    
                    lines.append(line)
                
                content = ''.join(lines)
                
                # If we hit the limit, indicate there's more content
                if len(lines) == limit and next(f, None) is not None:
                    content += "\n[...file content truncated, additional lines not shown...]\n"
                    
                return content
                
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return f"Error reading file: {str(e)}"
    
    def edit(self, file_path: str, old_string: str, new_string: str) -> str:
        """
        Edit a file by replacing a specific part of it.
        
        Args:
            file_path: Absolute path to the file to edit
            old_string: The text to replace
            new_string: The text to insert instead
            
        Returns:
            Result message
        """
        try:
            # Convert to absolute path if it's not already
            file_path = self._ensure_absolute_path(file_path)
            
            # Create a new file if it doesn't exist
            if not os.path.exists(file_path):
                if old_string:
                    return f"Error: File not found: {file_path}"
                
                # Create parent directory if needed
                parent_dir = os.path.dirname(file_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                
                # Create new file with content
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_string)
                    
                return f"Created new file: {file_path}"
            
            # Read current file content
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Check if old_string is present in file
            if old_string and old_string not in content:
                return f"Error: Target string not found in {file_path}"
            
            # Count occurrences to ensure uniqueness
            if old_string:
                # Count occurrences (handle empty string case)
                occurrences = content.count(old_string) if old_string else 0
                
                if occurrences > 1:
                    return f"Error: Found {occurrences} occurrences of the target string in {file_path}. The replacement must be unique."
                
                # Replace content
                new_content = content.replace(old_string, new_string, 1)
            else:
                # For new files with existing path
                new_content = new_string
            
            # Write updated content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return f"Successfully edited file: {file_path}"
            
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            return f"Error editing file: {str(e)}"
    
    def replace(self, file_path: str, content: str) -> str:
        """
        Completely replace file contents or create a new file.
        
        Args:
            file_path: Absolute path to the file to replace
            content: New content to write to the file
            
        Returns:
            Result message
        """
        try:
            # Convert to absolute path if it's not already
            file_path = self._ensure_absolute_path(file_path)
            
            # Create parent directory if needed
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # Write the content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            action = "Created" if not os.path.exists(file_path) else "Updated"
            return f"{action} file: {file_path}"
            
        except Exception as e:
            logger.error(f"Error replacing file {file_path}: {e}")
            return f"Error replacing file: {str(e)}"
    
    def glob_tool(self, pattern: str, path: Optional[str] = None) -> List[str]:
        """
        Find files matching a glob pattern.
        
        Args:
            pattern: The glob pattern to match against
            path: The directory to search in (defaults to current directory)
            
        Returns:
            List of matching file paths
        """
        try:
            # Use provided path or current directory
            base_path = path if path else self.current_dir
            
            # Convert to absolute path if it's not already
            base_path = self._ensure_absolute_path(base_path)
            
            if not os.path.isdir(base_path):
                return [f"Error: Path is not a directory: {base_path}"]
            
            # Create the full pattern
            if os.path.isabs(pattern):
                full_pattern = pattern
            else:
                full_pattern = os.path.join(base_path, pattern)
            
            # Find matching files
            matching_files = glob.glob(full_pattern, recursive=True)
            
            # Sort by modification time (newest first)
            matching_files.sort(key=os.path.getmtime, reverse=True)
            
            return matching_files if matching_files else [f"No files matching pattern: {pattern}"]
            
        except Exception as e:
            logger.error(f"Error during glob search: {e}")
            return [f"Error during search: {str(e)}"]
    
    def grep_tool(self, pattern: str, include: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search for content in files using regular expressions.
        
        Args:
            pattern: The regex pattern to search for
            include: File pattern to include (e.g., "*.py")
            path: Directory to search in (defaults to current directory)
            
        Returns:
            List of dictionaries with matching file info
        """
        try:
            # Use provided path or current directory
            base_path = path if path else self.current_dir
            
            # Convert to absolute path if it's not already
            base_path = self._ensure_absolute_path(base_path)
            
            if not os.path.isdir(base_path):
                return [{"error": f"Path is not a directory: {base_path}"}]
            
            # Compile regex for better performance
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return [{"error": f"Invalid regex pattern: {str(e)}"}]
            
            # Get files to search based on include pattern
            if include:
                file_paths = self.glob_tool(include, base_path)
                # Filter out error messages
                file_paths = [f for f in file_paths if not (isinstance(f, str) and f.startswith("Error:"))]
            else:
                # Walk directory tree
                file_paths = []
                for root, _, files in os.walk(base_path):
                    for file in files:
                        file_paths.append(os.path.join(root, file))
            
            # Search each file for the pattern
            results = []
            for file_path in file_paths:
                try:
                    # Skip binary files
                    if self._is_binary_file(file_path):
                        continue
                        
                    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                # Add match info
                                results.append({
                                    "file": file_path,
                                    "line_number": i,
                                    "line": line.strip(),
                                    "modified": os.path.getmtime(file_path)
                                })
                except (UnicodeDecodeError, IOError):
                    # Skip files that can't be read
                    continue
            
            # Sort by modification time (newest first)
            results.sort(key=lambda x: x.get("modified", 0), reverse=True)
            
            # Format results
            if not results:
                return [{"message": f"No matches found for pattern: {pattern}"}]
                
            return results
            
        except Exception as e:
            logger.error(f"Error during grep search: {e}")
            return [{"error": f"Error during search: {str(e)}"}]
    
    def ls(self, path: str) -> Dict[str, Any]:
        """
        List contents of a directory.
        
        Args:
            path: Absolute path to the directory to list
            
        Returns:
            Dictionary with directories and files
        """
        try:
            # Convert to absolute path if it's not already
            path = self._ensure_absolute_path(path)
            
            if not os.path.exists(path):
                return {"error": f"Path not found: {path}"}
                
            if not os.path.isdir(path):
                return {"error": f"Path is not a directory: {path}"}
            
            # Get directory contents
            entries = os.listdir(path)
            
            # Separate directories and files
            directories = []
            files = []
            
            for entry in sorted(entries):
                entry_path = os.path.join(path, entry)
                if os.path.isdir(entry_path):
                    directories.append(entry)
                else:
                    # Get file info
                    stats = os.stat(entry_path)
                    files.append({
                        "name": entry,
                        "size": stats.st_size,
                        "modified": stats.st_mtime
                    })
            
            return {
                "path": path,
                "directories": directories,
                "files": files
            }
            
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return {"error": f"Error listing directory: {str(e)}"}
    
    def _ensure_absolute_path(self, path: str) -> str:
        """Convert relative path to absolute path if needed."""
        if not os.path.isabs(path):
            return os.path.abspath(os.path.join(self.current_dir, path))
        return path
    
    def _is_binary_file(self, file_path: str) -> bool:
        """Check if a file is binary."""
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(4096)
                return b'\0' in chunk  # Simple heuristic for binary files
        except:
            return False
            
    def _is_image_file(self, file_path: str) -> bool:
        """Check if a file is an image based on extension."""
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp']
        return any(file_path.lower().endswith(ext) for ext in image_extensions)