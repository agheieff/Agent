import os
import logging
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel

from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from ..permissions import check_file_permission

logger = logging.getLogger(__name__)

class ReadFile(Operation):
    name = "read_file"
    description = "Reads content from a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file"),
        ArgumentDefinition(name="lines", type="integer", required=False, description="Maximum number of lines to read from the start (optional)")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path_str = args.path
        lines_to_read = args.lines
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing read_file: path='{path_str}', lines={lines_to_read}")

        # --- Permission & Path Validation ---
        if not check_file_permission(path_str, "read", file_perm_rules):
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent lacks 'read' permission for path: {path_str}")

        # Resolve *after* permission check to avoid resolving potentially sensitive paths
        try:
             file_path = Path(path_str).resolve(strict=True) # Ensures file exists
        except FileNotFoundError:
             raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File not found: {path_str}")
        except Exception as e: # Catch other resolution errors (e.g., permissions)
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Invalid path '{path_str}': {e}")

        if not file_path.is_file():
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a file: {path_str}")
        # --- End Validation ---

        try:
            content_lines = []
            with file_path.open('r', encoding='utf-8') as f:
                if lines_to_read is not None and lines_to_read > 0:
                    for i, line in enumerate(f):
                        if i >= lines_to_read:
                            break
                        content_lines.append(line.rstrip('\n'))
                    content = "\n".join(content_lines)
                else:
                    content = f.read()
            logger.debug(f"read_file successful for '{path_str}'")
            return OperationResult(success=True, data={"content": content})
        except UnicodeDecodeError as e:
            logger.warning(f"UnicodeDecodeError reading file '{path_str}': {e}")
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Cannot decode file '{path_str}' as UTF-8 text.") from e
        except Exception as e:
            logger.error(f"Error reading file '{path_str}': {e}", exc_info=True)
            # Use a more specific error if possible, otherwise generic failure
            if isinstance(e, PermissionError):
                 raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level read permission denied for: {path_str}") from e
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to read file '{path_str}': {str(e)}") from e


class WriteFile(Operation):
    name = "write_file"
    description = "Writes content to a specified file, optionally overwriting."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file"),
        ArgumentDefinition(name="content", type="string", required=True, description="Content to write"),
        ArgumentDefinition(name="overwrite", type="boolean", required=False, default=False, description="Overwrite if file exists (default: False)")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path_str = args.path
        content = args.content
        overwrite = args.overwrite
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing write_file: path='{path_str}', overwrite={overwrite}")

        # --- Permission & Path Validation ---
        if not check_file_permission(path_str, "write", file_perm_rules):
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent lacks 'write' permission for path: {path_str}")

        # Resolve parent directory first to check writability before file creation/overwrite check
        try:
             target_path = Path(path_str) # Don't resolve yet, need relative path for rule check
             dir_path = target_path.parent.resolve() # Resolve directory
        except Exception as e:
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Invalid parent path for '{path_str}': {e}")

        if not dir_path.is_dir():
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Parent directory does not exist or is not a directory: {dir_path}")
        # Basic OS check (might be redundant with agent perms, but good safeguard)
        if not os.access(dir_path, os.W_OK):
             raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level write permission denied for directory: {dir_path}")

        # Now handle the target file path resolution and existence check
        try:
            resolved_target_path = dir_path / target_path.name # Combine resolved dir with target filename
            if resolved_target_path.exists():
                if resolved_target_path.is_dir():
                    raise MCPError(ErrorCode.RESOURCE_EXISTS, f"Path exists and is a directory: {path_str}")
                if not overwrite:
                    raise MCPError(ErrorCode.RESOURCE_EXISTS, f"File exists and overwrite is False: {path_str}")
                # Check OS write permission on the existing file if overwriting
                if not os.access(resolved_target_path, os.W_OK):
                     raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level write permission denied for existing file: {path_str}")
            # If it doesn't exist, we already checked directory write permission.
        except Exception as e: # Catch potential issues during existence checks
             raise MCPError(ErrorCode.OPERATION_FAILED, f"Error checking target path '{path_str}': {e}")
        # --- End Validation ---

        try:
            with resolved_target_path.open('w', encoding='utf-8') as f:
                bytes_written = f.write(content)
            logger.info(f"Successfully wrote {bytes_written} bytes to '{path_str}' (resolved: {resolved_target_path})")
            return OperationResult(success=True, data={"bytes_written": bytes_written, "path": str(resolved_target_path.absolute())})
        except Exception as e:
            logger.error(f"Error writing to file '{path_str}': {e}", exc_info=True)
            if isinstance(e, PermissionError):
                 raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level write permission denied for: {path_str}") from e
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to write to file '{path_str}': {str(e)}") from e


class DeleteFile(Operation):
    name = "delete_file"
    description = "Deletes a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file to delete")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path_str = args.path
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing delete_file: path='{path_str}'")

        # --- Permission & Path Validation ---
        if not check_file_permission(path_str, "delete", file_perm_rules):
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent lacks 'delete' permission for path: {path_str}")

        try:
             file_path = Path(path_str).resolve(strict=True) # Ensures file exists before trying to delete
        except FileNotFoundError:
             # Decide on idempotency: either error or succeed silently if already gone.
             # Let's error for clarity.
             raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File not found: {path_str}")
        except Exception as e:
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Invalid path '{path_str}': {e}")

        if not file_path.is_file():
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a file: {path_str}")

        # Check OS-level permission on parent directory
        parent_dir = file_path.parent
        if not os.access(parent_dir, os.W_OK):
             raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level write permission denied for directory '{parent_dir}' (needed to delete file).")
        # --- End Validation ---

        try:
            file_path.unlink() # Use unlink for files
            logger.info(f"Successfully deleted file: '{path_str}' (resolved: {file_path})")
            return OperationResult(success=True, data={"path": str(file_path.absolute())})
        except Exception as e:
            logger.error(f"Error deleting file '{path_str}': {e}", exc_info=True)
            if isinstance(e, PermissionError):
                 raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level permission denied deleting: {path_str}") from e
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to delete file '{path_str}': {str(e)}") from e


class ListDirectory(Operation):
    name = "list_directory"
    description = "Lists the contents (files and subdirectories) of a specified directory."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=False, default=".", description="Directory path (default: current working directory)"),
        ArgumentDefinition(name="show_hidden", type="boolean", required=False, default=False, description="Include hidden items (starting with '.')")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path_str = args.path
        show_hidden = args.show_hidden
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing list_directory: path='{path_str}', show_hidden={show_hidden}")

        # --- Permission & Path Validation ---
        if not check_file_permission(path_str, "list", file_perm_rules):
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent lacks 'list' permission for directory: {path_str}")

        try:
             dir_path = Path(path_str).resolve(strict=True) # Ensures dir exists
        except FileNotFoundError:
             raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Directory not found: {path_str}")
        except Exception as e:
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Invalid path '{path_str}': {e}")

        if not dir_path.is_dir():
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a directory: {path_str}")
        # OS-level check
        if not os.access(dir_path, os.R_OK):
             raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level read permission denied for directory: {path_str}")
        # --- End Validation ---

        try:
            items = []
            for item_path in dir_path.iterdir():
                item_name = item_path.name
                if not show_hidden and item_name.startswith('.'):
                    continue

                # Granular permission check per item (optional, can be expensive)
                # item_path_str = str(item_path)
                # if not check_file_permission(item_path_str, "list_item", file_perm_rules): # Requires 'list_item' perm
                #      continue

                try:
                    # Use stat to determine type without following symlinks (lstat) if needed
                    item_type = "directory" if item_path.is_dir() else "file"
                    if item_path.is_symlink():
                        item_type = "symlink" # Distinguish symlinks
                except OSError:
                    item_type = "unknown/inaccessible"

                items.append({"name": item_name, "type": item_type})

            # Sort primarily by type (directories first), then by name
            items.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))

            logger.debug(f"list_directory successful for '{path_str}'")
            return OperationResult(success=True, data={"path": str(dir_path.absolute()), "contents": items})
        except Exception as e:
            logger.error(f"Error listing directory '{path_str}': {e}", exc_info=True)
            if isinstance(e, PermissionError):
                 raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS-level permission denied listing: {path_str}") from e
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to list directory '{path_str}': {str(e)}") from e
