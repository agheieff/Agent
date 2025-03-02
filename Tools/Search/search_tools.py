import os
import re
import glob
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class SearchTools:
    """
    Implements file system search capabilities for the agent.
    Includes glob pattern matching and content searching (grep).
    """
    
    def __init__(self):
        self.current_dir = os.getcwd()
    
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