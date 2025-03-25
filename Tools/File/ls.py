
import os
from pathlib import Path
from Tools.base import Tool, Argument, ToolConfig, ErrorCodes, ToolResult, ArgumentType

class ListDirectory(Tool):
    def __init__(self):
        config = ToolConfig(
            test_mode=True,
            needs_sudo=False
        )
        super().__init__(
            name="ls",
            description="Lists the contents of a directory",
            args=[
                Argument(
                    name="path",
                    arg_type=ArgumentType.STRING,
                    description="The directory path to list",
                    optional=True,
                    default="."
                ),
                Argument(
                    name="show_hidden",
                    arg_type=ArgumentType.BOOLEAN,
                    description="Whether to show hidden files (those starting with .)",
                    optional=True,
                    default=False
                ),
                Argument(
                    name="recursive",
                    arg_type=ArgumentType.BOOLEAN,
                    description="Whether to list subdirectories recursively",
                    optional=True,
                    default=False
                ),
                Argument(
                    name="long_format",
                    arg_type=ArgumentType.BOOLEAN,
                    description="Whether to use long listing format (similar to ls -l)",
                    optional=True,
                    default=False
                )
            ],
            config=config
        )

    def _run(self, args, **kwargs):
        path = args.get("path", ".")
        show_hidden = args.get("show_hidden", False)
        recursive = args.get("recursive", False)
        long_format = args.get("long_format", False)
        
        if not os.path.exists(path):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_NOT_FOUND, message=f"Path '{path}' does not exist.")
        if not os.path.isdir(path):
            return ToolResult(success=False, code=ErrorCodes.RESOURCE_NOT_FOUND, message=f"Path '{path}' is not a directory.")
        if not os.access(path, os.R_OK):
            return ToolResult(success=False, code=ErrorCodes.PERMISSION_DENIED, message=f"No read permission for directory '{path}'.")
        
        try:
            if recursive:
                listing = self._list_recursive(path, show_hidden, long_format)
            else:
                listing = self._list_directory(path, show_hidden, long_format)
            return ToolResult(success=True, code=ErrorCodes.SUCCESS, message=listing)
        except Exception as e:
            return ToolResult(success=False, code=ErrorCodes.UNKNOWN_ERROR, message=f"Error listing directory: {str(e)}")
    
    def _list_directory(self, path, show_hidden, long_format):
        items = os.listdir(path)
        if not show_hidden:
            items = [item for item in items if not item.startswith('.')]
        dirs = []
        files = []
        for item in items:
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                dirs.append(item)
            else:
                files.append(item)
        dirs.sort()
        files.sort()
        sorted_items = dirs + files
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
        result = []
        for root, dirs, files in os.walk(path):
            if not show_hidden:
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                files = [f for f in files if not f.startswith('.')]
            dirs.sort()
            files.sort()
            rel_path = os.path.relpath(root, start=os.path.dirname(path))
            if rel_path == '.':
                rel_path = os.path.basename(path) or path
            result.append(f"\nDirectory: {rel_path}")
            if long_format:
                if files or dirs:
                    result.append(f"{'Type':<6} {'Size':<10} {'Name':<30}")
                    result.append("-" * 50)
                for d in dirs:
                    result.append(f"{'DIR':<6} {'<DIR>':<10} {d:<30}")
                for f in files:
                    file_path = os.path.join(root, f)
                    size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
                    result.append(f"{'FILE':<6} {size:,}<10 {f:<30}")
            else:
                for d in dirs:
                    result.append(f"{d}/")
                for f in files:
                    result.append(f)
        return "\n".join(result)
