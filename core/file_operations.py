import os
import re
import json
import logging
import glob
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Union, Tuple

logger = logging.getLogger(__name__)

class NotebookReader:
    """
    Reader for Jupyter notebook (.ipynb) files with support for 
    reading, parsing, and extracting cell contents
    """
    
    def __init__(self):
        self.cell_types = ["code", "markdown", "raw"]
    
    def read_notebook(self, file_path: str) -> Dict[str, Any]:
        """
        Read a Jupyter notebook file and return its contents
        
        Args:
            file_path: Path to the notebook file
            
        Returns:
            Dictionary with notebook metadata and cells
        """
        try:
            # Convert to absolute path if it's not already
            file_path = os.path.abspath(file_path)
            
            if not os.path.exists(file_path):
                return {"error": f"Notebook not found: {file_path}"}
                
            if not file_path.endswith('.ipynb'):
                return {"error": f"Not a Jupyter notebook file: {file_path}"}
                
            # Read and parse notebook
            with open(file_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)
                
            # Extract metadata and cells
            metadata = notebook.get('metadata', {})
            cells = notebook.get('cells', [])
            
            # Process cells
            processed_cells = []
            for i, cell in enumerate(cells):
                cell_type = cell.get('cell_type', '')
                source = ''.join(cell.get('source', []))
                outputs = cell.get('outputs', [])
                execution_count = cell.get('execution_count', None)
                
                # Process outputs for code cells
                processed_outputs = []
                if cell_type == 'code':
                    for output in outputs:
                        output_type = output.get('output_type', '')
                        
                        if output_type == 'stream':
                            # Text output (stdout/stderr)
                            name = output.get('name', 'stdout')
                            text = ''.join(output.get('text', []))
                            processed_outputs.append({
                                'type': name,
                                'content': text
                            })
                        elif output_type in ('execute_result', 'display_data'):
                            # Result data
                            data = output.get('data', {})
                            
                            # Text/plain is the most basic representation
                            if 'text/plain' in data:
                                text = ''.join(data['text/plain'])
                                processed_outputs.append({
                                    'type': 'result',
                                    'content': text
                                })
                            
                            # Handle other mime types
                            for mime in data:
                                if mime != 'text/plain':
                                    if mime == 'text/html':
                                        content = ''.join(data[mime])
                                        processed_outputs.append({
                                            'type': 'html',
                                            'content': content
                                        })
                                    elif mime == 'image/png':
                                        processed_outputs.append({
                                            'type': 'image',
                                            'format': 'png',
                                            'content': '[image data]'
                                        })
                                    else:
                                        processed_outputs.append({
                                            'type': mime,
                                            'content': '[data]'
                                        })
                        elif output_type == 'error':
                            # Error output
                            ename = output.get('ename', '')
                            evalue = output.get('evalue', '')
                            traceback = output.get('traceback', [])
                            
                            processed_outputs.append({
                                'type': 'error',
                                'ename': ename,
                                'evalue': evalue,
                                'traceback': traceback
                            })
                
                # Add processed cell
                processed_cells.append({
                    'index': i,
                    'type': cell_type,
                    'source': source,
                    'outputs': processed_outputs,
                    'execution_count': execution_count
                })
                
            return {
                'path': file_path,
                'metadata': metadata,
                'cells': processed_cells,
                'cell_count': len(cells)
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error in notebook {file_path}: {e}")
            return {"error": f"Invalid notebook format: {str(e)}"}
        except Exception as e:
            logger.error(f"Error reading notebook {file_path}: {e}")
            return {"error": f"Error reading notebook: {str(e)}"}
    
    def edit_notebook_cell(self, file_path: str, cell_index: int, 
                         new_source: str, cell_type: Optional[str] = None,
                         mode: str = "replace") -> Dict[str, Any]:
        """
        Edit a cell in a Jupyter notebook
        
        Args:
            file_path: Path to the notebook file
            cell_index: Index of the cell to edit (0-based)
            new_source: New content for the cell
            cell_type: New cell type (code, markdown, raw) - only used for 'insert' mode
            mode: Operation mode - 'replace', 'insert', or 'delete'
            
        Returns:
            Dictionary with status and info
        """
        try:
            # Convert to absolute path if it's not already
            file_path = os.path.abspath(file_path)
            
            if not os.path.exists(file_path):
                return {"error": f"Notebook not found: {file_path}"}
                
            if not file_path.endswith('.ipynb'):
                return {"error": f"Not a Jupyter notebook file: {file_path}"}
                
            # Create backup before modifying
            backup_path = f"{file_path}.bak"
            shutil.copy2(file_path, backup_path)
            
            # Read notebook
            with open(file_path, 'r', encoding='utf-8') as f:
                notebook = json.load(f)
                
            cells = notebook.get('cells', [])
            
            # Check cell index
            if mode != "insert" and (cell_index < 0 or cell_index >= len(cells)):
                return {"error": f"Cell index {cell_index} out of range (0-{len(cells)-1})"}
                
            if mode == "replace":
                # Replace cell content
                cells[cell_index]['source'] = self._convert_to_multiline_format(new_source)
                
                # Keep the existing cell type
                result = {"status": "success", "action": "replaced", "index": cell_index}
                
            elif mode == "insert":
                # Validate cell type for new cell
                if not cell_type:
                    cell_type = "code"  # Default
                    
                if cell_type not in self.cell_types:
                    return {"error": f"Invalid cell type: {cell_type}. Must be one of: {', '.join(self.cell_types)}"}
                    
                # Create new cell
                new_cell = {
                    "cell_type": cell_type,
                    "source": self._convert_to_multiline_format(new_source),
                    "metadata": {}
                }
                
                # Add outputs array for code cells
                if cell_type == "code":
                    new_cell["outputs"] = []
                    new_cell["execution_count"] = None
                
                # Insert at the specified position
                if cell_index >= len(cells):
                    cells.append(new_cell)
                else:
                    cells.insert(cell_index, new_cell)
                    
                result = {"status": "success", "action": "inserted", "index": cell_index, "type": cell_type}
                
            elif mode == "delete":
                # Delete the cell
                del cells[cell_index]
                result = {"status": "success", "action": "deleted", "index": cell_index}
                
            else:
                return {"error": f"Invalid mode: {mode}. Must be one of: replace, insert, delete"}
                
            # Write modified notebook
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(notebook, f, indent=2)
                
            # Remove backup if everything succeeded
            # os.remove(backup_path)  # Keep backups for safety
            
            return result
            
        except json.JSONDecodeError as e:
            # Restore from backup if possible
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
                
            logger.error(f"JSON decode error in notebook {file_path}: {e}")
            return {"error": f"Invalid notebook format: {str(e)}", "restored_from_backup": True}
            
        except Exception as e:
            # Restore from backup if possible
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, file_path)
                
            logger.error(f"Error editing notebook {file_path}: {e}")
            return {"error": f"Error editing notebook: {str(e)}", "restored_from_backup": True}
            
    def _convert_to_multiline_format(self, text: str) -> List[str]:
        """Convert a string to the multiline format used in notebooks"""
        lines = text.split('\n')
        return [line + '\n' for line in lines[:-1]] + ([lines[-1]] if lines else [])


class FileOperations:
    """
    Provides file operation capabilities similar to Claude Code functions:
    - View: Read file contents
    - Edit: Modify specific parts of files
    - Replace: Completely replace file contents
    - GlobTool: Find files matching a pattern
    - GrepTool: Search for content within files
    - LS: List directory contents
    - NotebookReader: Read and edit Jupyter notebooks
    - FileDiff: Compare files
    - FileMove: Move and rename files
    - FileBackup: Create and restore backups
    """
    
    def __init__(self):
        self.current_dir = os.getcwd()
        self.notebook_reader = NotebookReader()
        # Set to track files that have been read (for safety check)
        self.viewed_files: Set[str] = set()
    
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
                # Add to viewed files even though it's an image
                self.viewed_files.add(file_path)
                return f"[Image file: {file_path}]"
                
            # Handle binary files
            if self._is_binary_file(file_path):
                # Add to viewed files even though it's binary
                self.viewed_files.add(file_path)
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
                
                # Track this file as having been viewed
                self.viewed_files.add(file_path)
                    
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
                
                # Track as viewed since we're creating it
                self.viewed_files.add(file_path)
                return f"Created new file: {file_path}"
            
            # Safety check: Verify file has been read before
            if file_path not in self.viewed_files:
                warning = f"Warning: File {file_path} has not been read yet. "
                warning += "Consider viewing it first with view() to avoid errors. "
                warning += "This is a safety check, not a hard restriction."
                logger.warning(warning)
                # We don't block the edit, just warn about it
            
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
            
            # Mark as viewed since we've now interacted with it
            self.viewed_files.add(file_path)
            
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
            
            # Safety check if file exists but hasn't been read
            if os.path.exists(file_path) and file_path not in self.viewed_files:
                warning = f"Warning: File {file_path} has not been read yet before replacing. "
                warning += "Consider viewing it first with view() to avoid errors. "
                warning += "This is a safety check, not a hard restriction."
                logger.warning(warning)
                # We don't block the edit, just warn about it
            
            # Create parent directory if needed
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # Write the content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Mark as viewed since we've now interacted with it
            self.viewed_files.add(file_path)
            
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
        
    def read_notebook(self, notebook_path: str) -> Dict[str, Any]:
        """
        Read a Jupyter notebook file
        
        Args:
            notebook_path: Path to the notebook file
            
        Returns:
            Dictionary with notebook contents
        """
        return self.notebook_reader.read_notebook(notebook_path)
        
    def edit_notebook_cell(self, notebook_path: str, cell_index: int, 
                          new_source: str, cell_type: Optional[str] = None,
                          mode: str = "replace") -> Dict[str, Any]:
        """
        Edit a cell in a Jupyter notebook
        
        Args:
            notebook_path: Path to the notebook file
            cell_index: Index of the cell to edit (0-based)
            new_source: New content for the cell
            cell_type: New cell type (only for 'insert' mode)
            mode: Operation mode - 'replace', 'insert', or 'delete'
            
        Returns:
            Dictionary with status and info
        """
        return self.notebook_reader.edit_notebook_cell(
            notebook_path, cell_index, new_source, cell_type, mode
        )
        
    def move_file(self, source_path: str, target_path: str, overwrite: bool = False) -> Dict[str, Any]:
        """
        Move or rename a file
        
        Args:
            source_path: Path to the file to move
            target_path: Destination path
            overwrite: Whether to overwrite existing destination file
            
        Returns:
            Dictionary with operation status
        """
        try:
            # Convert to absolute paths if not already
            source_path = self._ensure_absolute_path(source_path)
            target_path = self._ensure_absolute_path(target_path)
            
            # Check if source exists
            if not os.path.exists(source_path):
                return {"error": f"Source file not found: {source_path}"}
                
            # Check if target already exists
            if os.path.exists(target_path) and not overwrite:
                return {"error": f"Target already exists: {target_path}. Use overwrite=True to replace."}
                
            # Create target directory if needed
            target_dir = os.path.dirname(target_path)
            if target_dir and not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                
            # Move the file
            shutil.move(source_path, target_path)
            
            return {
                "status": "success",
                "source": source_path,
                "target": target_path,
                "operation": "move"
            }
            
        except Exception as e:
            logger.error(f"Error moving file from {source_path} to {target_path}: {e}")
            return {"error": f"Error moving file: {str(e)}"}
            
    def backup_file(self, file_path: str, backup_suffix: str = None) -> Dict[str, Any]:
        """
        Create a backup of a file
        
        Args:
            file_path: Path to the file to backup
            backup_suffix: Suffix to add to backup file (default: timestamp)
            
        Returns:
            Dictionary with operation status and backup path
        """
        try:
            # Convert to absolute path if not already
            file_path = self._ensure_absolute_path(file_path)
            
            # Check if source exists
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}
                
            # Generate backup path
            if backup_suffix is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_suffix = f".bak_{timestamp}"
                
            backup_path = f"{file_path}{backup_suffix}"
            
            # Create backup
            shutil.copy2(file_path, backup_path)
            
            return {
                "status": "success",
                "original": file_path,
                "backup": backup_path,
                "operation": "backup"
            }
            
        except Exception as e:
            logger.error(f"Error backing up file {file_path}: {e}")
            return {"error": f"Error backing up file: {str(e)}"}
            
    def compare_files(self, file1_path: str, file2_path: str, 
                     max_lines: int = 100) -> Dict[str, Any]:
        """
        Compare two text files and show differences
        
        Args:
            file1_path: Path to first file
            file2_path: Path to second file
            max_lines: Maximum number of diff lines to return
            
        Returns:
            Dictionary with differences
        """
        try:
            # Convert to absolute paths if not already
            file1_path = self._ensure_absolute_path(file1_path)
            file2_path = self._ensure_absolute_path(file2_path)
            
            # Check if files exist
            if not os.path.exists(file1_path):
                return {"error": f"File 1 not found: {file1_path}"}
                
            if not os.path.exists(file2_path):
                return {"error": f"File 2 not found: {file2_path}"}
                
            # Skip binary files
            if self._is_binary_file(file1_path) or self._is_binary_file(file2_path):
                return {"error": "Cannot compare binary files"}
                
            # Read file contents
            with open(file1_path, 'r', encoding='utf-8', errors='replace') as f:
                file1_lines = f.readlines()
                
            with open(file2_path, 'r', encoding='utf-8', errors='replace') as f:
                file2_lines = f.readlines()
                
            # Compare file sizes first
            file1_size = len(file1_lines)
            file2_size = len(file2_lines)
            
            # Find common prefix and suffix
            common_prefix = 0
            for i in range(min(file1_size, file2_size)):
                if file1_lines[i] != file2_lines[i]:
                    break
                common_prefix += 1
                
            common_suffix = 0
            for i in range(1, min(file1_size - common_prefix, file2_size - common_prefix) + 1):
                if file1_lines[file1_size - i] != file2_lines[file2_size - i]:
                    break
                common_suffix += 1
                
            # Create a simple diff output
            diff_lines = []
            
            # Show context before differences
            context_start = max(0, common_prefix - 3)
            context_lines = min(common_prefix, 3)
            
            if context_lines > 0:
                diff_lines.append(f"... {context_lines} identical lines ...")
                for i in range(context_start, common_prefix):
                    diff_lines.append(f"  {i+1}: {file1_lines[i].rstrip()}")
                    
            # Show differences
            for i in range(common_prefix, file1_size - common_suffix):
                diff_lines.append(f"- {i+1}: {file1_lines[i].rstrip()}")
                
            for i in range(common_prefix, file2_size - common_suffix):
                diff_lines.append(f"+ {i+1}: {file2_lines[i].rstrip()}")
                
            # Show context after differences
            if common_suffix > 0:
                context_end = min(3, common_suffix)
                diff_lines.append(f"... {context_end} identical lines ...")
                for i in range(1, context_end + 1):
                    line_num = file1_size - common_suffix + i - 1
                    diff_lines.append(f"  {line_num+1}: {file1_lines[line_num].rstrip()}")
                    
            # Limit output size
            if len(diff_lines) > max_lines:
                half_lines = max_lines // 2
                first_half = diff_lines[:half_lines]
                second_half = diff_lines[-half_lines:]
                diff_lines = first_half + [f"... {len(diff_lines) - max_lines} lines omitted ..."] + second_half
                
            return {
                "status": "success",
                "file1": file1_path,
                "file2": file2_path,
                "file1_lines": file1_size,
                "file2_lines": file2_size,
                "identical": file1_lines == file2_lines,
                "common_prefix": common_prefix,
                "common_suffix": common_suffix,
                "diff": "\n".join(diff_lines)
            }
            
        except Exception as e:
            logger.error(f"Error comparing files {file1_path} and {file2_path}: {e}")
            return {"error": f"Error comparing files: {str(e)}"}