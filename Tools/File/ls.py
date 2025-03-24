import os
from pathlib import Path
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ArgumentType


class ListDirectory(Tool):
    def __init__(self):
        config = ToolConfig(
            allowed_in_test_mode=True,
            requires_sudo=False
        )
        
        super().__init__(
            name="ls",
            description="Lists the contents of a directory",
            help_text="Lists files and directories in the specified path with various formatting options.",
            arguments=[
                Argument(
                    name="path",
                    arg_type=ArgumentType.STRING,
                    is_optional=True,
                    default_value=".",
                    description="The directory path to list"
                ),
                Argument(
                    name="show_hidden",
                    arg_type=ArgumentType.BOOLEAN,
                    is_optional=True,
                    default_value=False,
                    description="Whether to show hidden files (those starting with .)"
                ),
                Argument(
                    name="recursive",
                    arg_type=ArgumentType.BOOLEAN,
                    is_optional=True,
                    default_value=False,
                    description="Whether to recursively list subdirectories"
                ),
                Argument(
                    name="long_format",
                    arg_type=ArgumentType.BOOLEAN,
                    is_optional=True,
                    default_value=False,
                    description="Whether to use long listing format (similar to ls -l)"
                )
            ],
            config=config
        )

    def _execute(self, path=".", show_hidden=False, recursive=False, long_format=False):
        """
        Lists the contents of a directory.
        
        Args:
            path: Directory path to list
            show_hidden: Whether to show hidden files
            recursive: Whether to list subdirectories recursively
            long_format: Whether to use long listing format
            
        Returns:
            A tuple containing the error code and the directory listing
        """
        # Validate if the path exists
        if not os.path.exists(path):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"Path '{path}' does not exist."
        
        # Validate if the path is a directory
        if not os.path.isdir(path):
            return ErrorCodes.RESOURCE_NOT_FOUND, f"Path '{path}' is not a directory."
        
        # Validate if the path is readable
        if not os.access(path, os.R_OK):
            return ErrorCodes.PERMISSION_DENIED, f"No read permission for directory '{path}'."
        
        try:
            # Get the listing
            if recursive:
                listing = self._list_recursive(path, show_hidden, long_format)
            else:
                listing = self._list_directory(path, show_hidden, long_format)
            
            return ErrorCodes.SUCCESS, listing
        
        except Exception as e:
            return ErrorCodes.UNKNOWN_ERROR, f"Error listing directory: {str(e)}"
    
    def _list_directory(self, path, show_hidden, long_format):
        """
        Lists a single directory.
        
        Args:
            path: Directory path
            show_hidden: Whether to show hidden files
            long_format: Whether to use long listing format
            
        Returns:
            A formatted string containing the directory listing
        """
        # Get all items in the directory
        items = os.listdir(path)
        
        # Filter out hidden files if not showing them
        if not show_hidden:
            items = [item for item in items if not item.startswith('.')]
        
        # Sort items (directories first, then files)
        dirs = []
        files = []
        
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                dirs.append(item)
            else:
                files.append(item)
        
        # Sort alphabetically within each category
        dirs.sort()
        files.sort()
        
        # Combine sorted lists
        sorted_items = dirs + files
        
        # Format the listing
        if long_format:
            result = []
            result.append(f"Directory listing of {os.path.abspath(path)}:")
            result.append(f"{'Type':<6} {'Size':<10} {'Name':<30}")
            result.append("-" * 50)
            
            for item in sorted_items:
                item_path = os.path.join(path, item)
                is_dir = os.path.isdir(item_path)
                size = os.path.getsize(item_path) if os.path.exists(item_path) else 0
                
                item_type = "DIR" if is_dir else "FILE"
                size_str = f"{size:,}" if not is_dir else "<DIR>"
                
                result.append(f"{item_type:<6} {size_str:<10} {item:<30}")
            
            return "\n".join(result)
        else:
            # Simple format - just list the names with directories marked
            result = []
            result.append(f"Directory listing of {os.path.abspath(path)}:")
            
            for item in sorted_items:
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    result.append(f"{item}/")
                else:
                    result.append(item)
            
            return "\n".join(result)
    
    def _list_recursive(self, path, show_hidden, long_format):
        """
        Lists a directory recursively.
        
        Args:
            path: Directory path
            show_hidden: Whether to show hidden files
            long_format: Whether to use long listing format
            
        Returns:
            A formatted string containing the recursive directory listing
        """
        result = []
        
        # Walk through the directory tree
        for root, dirs, files in os.walk(path):
            # Filter out hidden directories if not showing hidden items
            if not show_hidden:
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                files = [f for f in files if not f.startswith('.')]
            
            # Sort directories and files
            dirs.sort()
            files.sort()
            
            # Get relative path for display
            rel_path = os.path.relpath(root, start=os.path.dirname(path))
            if rel_path == '.':
                rel_path = os.path.basename(path) or path
            
            # Add the directory header
            result.append(f"\nDirectory: {rel_path}")
            
            # Format the listing for this directory
            if long_format:
                if files or dirs:
                    result.append(f"{'Type':<6} {'Size':<10} {'Name':<30}")
                    result.append("-" * 50)
                
                # List directories first
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    result.append(f"{'DIR':<6} {'<DIR>':<10} {d:<30}")
                
                # Then list files
                for f in files:
                    file_path = os.path.join(root, f)
                    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    result.append(f"{'FILE':<6} {size:,}<10 {f:<30}")
            else:
                # Simple format
                for d in dirs:
                    result.append(f"{d}/")
                for f in files:
                    result.append(f)
        
        return "\n".join(result) 