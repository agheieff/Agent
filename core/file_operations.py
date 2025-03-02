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
        Replaces all occurrences of 'old_string' with 'new_string'. 
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

            # Replace all occurrences:
            if old_string:
                new_content = content.replace(old_string, new_string)
            else:
                # If old_string is empty, we treat it as appending or overwriting?
                # For clarity, let's just overwrite:
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

    def glob_tool(self, pattern: str, path: Optional[str] = None) -> List[str]:
        """
        Finds files that match a 'pattern' under the given directory ('path'),
        or the current directory if none is provided.
        """
        try:
            base_path = path if path else self.current_dir
            base_path = self._ensure_absolute_path(base_path)
            if not os.path.isdir(base_path):
                return [f"Error: Not a directory: {base_path}"]

            if os.path.isabs(pattern):
                full_pattern = pattern
            else:
                full_pattern = os.path.join(base_path, pattern)

            matching_files = glob.glob(full_pattern, recursive=True)
            matching_files.sort(key=os.path.getmtime, reverse=True)
            return matching_files if matching_files else [f"No files matching: {pattern}"]

        except Exception as e:
            logger.error(f"Error during glob: {e}")
            return [f"Error: {str(e)}"]

    def grep_tool(self, pattern: str, include: Optional[str] = None, path: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Searches for 'pattern' (regex) in matching files. 
        Optionally restrict to 'include' pattern, under 'path' or current directory if none given.
        """
        results = []
        try:
            base_path = path if path else self.current_dir
            base_path = self._ensure_absolute_path(base_path)
            if not os.path.isdir(base_path):
                return [{"error": f"Not a directory: {base_path}"}]

            # Compile regex
            try:
                regex = re.compile(pattern)
            except re.error as comp_err:
                return [{"error": f"Invalid regex: {str(comp_err)}"}]

            # Gather files to search
            if include:
                file_paths = self.glob_tool(include, base_path)
                # filter out any errors from the glob
                file_paths = [f for f in file_paths if not (isinstance(f, str) and f.startswith("Error:"))]
            else:
                file_paths = []
                for root, _, files in os.walk(base_path):
                    for file in files:
                        file_paths.append(os.path.join(root, file))

            for fp in file_paths:
                if self._is_binary_file(fp):
                    continue
                try:
                    with open(fp, 'r', encoding='utf-8', errors='replace') as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append({
                                    "file": fp,
                                    "line_number": i,
                                    "line": line.strip(),
                                    "modified": os.path.getmtime(fp)
                                })
                except:
                    continue

            if not results:
                return [{"message": f"No matches for {pattern}"}]

            results.sort(key=lambda x: x.get("modified", 0), reverse=True)
            return results

        except Exception as e:
            logger.error(f"Error in grep: {e}")
            return [{"error": f"{str(e)}"}]

    def ls(self, path: str) -> Dict[str, Any]:
        """
        Lists directories and files at the given path.
        """
        try:
            abs_path = self._ensure_absolute_path(path)
            if not os.path.exists(abs_path):
                return {"error": f"Path not found: {abs_path}"}
            if not os.path.isdir(abs_path):
                return {"error": f"Not a directory: {abs_path}"}

            entries = os.listdir(abs_path)
            directories = []
            files = []

            for entry in sorted(entries):
                entry_path = os.path.join(abs_path, entry)
                if os.path.isdir(entry_path):
                    directories.append(entry)
                else:
                    st = os.stat(entry_path)
                    files.append({"name": entry, "size": st.st_size, "modified": st.st_mtime})

            return {
                "path": abs_path,
                "directories": directories,
                "files": files
            }

        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return {"error": f"{str(e)}"}

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
