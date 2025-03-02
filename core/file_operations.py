import os
import re
import json
import logging
import glob
from pathlib import Path
from typing import List, Dict, Optional, Any, Set

logger = logging.getLogger(__name__)

class FileOperations:
    def __init__(self):
        self.current_dir = os.getcwd()
        self.viewed_files: Set[str] = set()

    def view(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        try:
            file_path = self._ensure_absolute_path(file_path)
            if not os.path.exists(file_path):
                return f"Error: File not found: {file_path}"
            if os.path.isdir(file_path):
                return f"Error: {file_path} is a directory"
            if self._is_image_file(file_path):
                self.viewed_files.add(file_path)
                return f"[Image file: {file_path}]"
            if self._is_binary_file(file_path):
                self.viewed_files.add(file_path)
                return f"[Binary file: {file_path}]"
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                for _ in range(offset):
                    next(f, None)
                lines = []
                for _ in range(limit):
                    line = next(f, None)
                    if line is None:
                        break
                    if len(line) > 2000:
                        line = line[:2000] + " [line truncated]\n"
                    lines.append(line)
                content = ''.join(lines)
                if len(lines) == limit and next(f, None) is not None:
                    content += "\n[...file content truncated...]\n"
                self.viewed_files.add(file_path)
                return content
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return f"Error reading file: {str(e)}"

    def edit(self, file_path: str, old_string: str, new_string: str) -> str:
        try:
            file_path = self._ensure_absolute_path(file_path)
            if not os.path.exists(file_path):
                if old_string:
                    return f"Error: File not found: {file_path}"
                parent_dir = os.path.dirname(file_path)
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_string)
                self.viewed_files.add(file_path)
                return f"Created new file: {file_path}"
            if file_path not in self.viewed_files:
                logger.warning(f"Warning: Editing file that wasn't viewed: {file_path}")
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            if old_string and old_string not in content:
                return f"Error: Target string not found in {file_path}"
            # Remove uniqueness restriction; replace all occurrences
            if old_string:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = new_string
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            self.viewed_files.add(file_path)
            return f"Successfully edited file: {file_path}"
        except Exception as e:
            logger.error(f"Error editing file {file_path}: {e}")
            return f"Error editing file: {str(e)}"

    def replace(self, file_path: str, content: str) -> str:
        try:
            file_path = self._ensure_absolute_path(file_path)
            if os.path.exists(file_path) and file_path not in self.viewed_files:
                logger.warning(f"Warning: Replacing file not previously viewed: {file_path}")
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.viewed_files.add(file_path)
            return f"Updated file: {file_path}"
        except Exception as e:
            logger.error(f"Error replacing file {file_path}: {e}")
            return f"Error replacing file: {str(e)}"

    def glob_tool(self, pattern: str, path: Optional[str] = None) -> List[str]:
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
        results = []
        try:
            base_path = path if path else self.current_dir
            base_path = self._ensure_absolute_path(base_path)
            if not os.path.isdir(base_path):
                return [{"error": f"Not a directory: {base_path}"}]
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return [{"error": f"Invalid regex: {str(e)}"}]
            if include:
                file_paths = self.glob_tool(include, base_path)
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
        try:
            path = self._ensure_absolute_path(path)
            if not os.path.exists(path):
                return {"error": f"Path not found: {path}"}
            if not os.path.isdir(path):
                return {"error": f"Not a directory: {path}"}
            entries = os.listdir(path)
            directories = []
            files = []
            for entry in sorted(entries):
                entry_path = os.path.join(path, entry)
                if os.path.isdir(entry_path):
                    directories.append(entry)
                else:
                    st = os.stat(entry_path)
                    files.append({"name": entry, "size": st.st_size, "modified": st.st_mtime})
            return {"path": path, "directories": directories, "files": files}
        except Exception as e:
            logger.error(f"Error listing directory {path}: {e}")
            return {"error": f"{str(e)}"}

    def _ensure_absolute_path(self, path: str) -> str:
        if not os.path.isabs(path):
            return os.path.abspath(os.path.join(self.current_dir, path))
        return path

    def _is_binary_file(self, file_path: str) -> bool:
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(4096)
                return b'\0' in chunk
        except:
            return False

    def _is_image_file(self, file_path: str) -> bool:
        return any(file_path.lower().endswith(ext) for ext in ['.jpg','.jpeg','.png','.gif','.bmp','.svg','.webp'])
