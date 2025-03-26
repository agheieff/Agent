import os
import logging
from pathlib import Path
from typing import Optional, List, Dict # Added Dict
from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from ..permissions import check_file_permission # Import permission checker
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ReadFile(Operation):
    name = "read_file"
    description = "Reads content from a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file"),
        ArgumentDefinition(name="lines", type="integer", required=False, description="Number of lines to read (optional)")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path = args.path
        lines_to_read = args.lines
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []
        content_lines = []

        logger.debug(f"Executing read_file: path='{path}', lines={lines_to_read}, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")

        # --- Permission Check ---
        if not check_file_permission(path, "read", file_perm_rules):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent does not have 'read' permission for path prefix related to: {path}")
        # --- ---

        if not os.path.exists(path):
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File not found: {path}")
        if not os.path.isfile(path):
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a file: {path}")
        if not os.access(path, os.R_OK):
            # This OS-level check might be redundant depending on check_file_permission,
            # but provides a fallback OS check.
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"OS-level read permission denied for file: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                if lines_to_read is not None and lines_to_read > 0:
                    try:
                        for _ in range(lines_to_read):
                             line = next(f)
                             content_lines.append(line.rstrip('\n'))
                    except StopIteration:
                         pass # EOF reached, return what was read
                    content = "\n".join(content_lines)
                else:
                    content = f.read()
            logger.debug(f"read_file successful for '{path}'")
            return OperationResult(success=True, data={"content": content})
        except UnicodeDecodeError as e:
            logger.warning(f"UnicodeDecodeError reading file '{path}': {e}")
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Cannot decode file '{path}' as UTF-8 text.") from e
        except Exception as e:
            logger.error(f"Error reading file '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to read file '{path}': {str(e)}") from e


class WriteFile(Operation):
    name = "write_file"
    description = "Writes content to a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file"),
        ArgumentDefinition(name="content", type="string", required=True, description="Content to write"),
        ArgumentDefinition(name="overwrite", type="boolean", required=False, default=False, description="Overwrite if file exists (default: False)")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path = args.path
        content = args.content
        overwrite = args.overwrite
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing write_file: path='{path}', overwrite={overwrite}, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")

        # --- Permission Check ---
        if not check_file_permission(path, "write", file_perm_rules):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent does not have 'write' permission for path prefix related to: {path}")
        # --- ---

        file_path = Path(path)
        dir_path = file_path.parent

        if not dir_path.exists():
             raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Directory does not exist: {dir_path}")
        if not dir_path.is_dir():
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Parent path is not a directory: {dir_path}")
        # OS-level check (might be redundant with check_file_permission on path)
        if not os.access(dir_path, os.W_OK):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"OS-level write permission denied for directory: {dir_path}")

        if file_path.exists():
            if file_path.is_dir():
                 raise MCPError(ErrorCode.RESOURCE_EXISTS, f"Path exists and is a directory: {path}")
            if not overwrite:
                 raise MCPError(ErrorCode.RESOURCE_EXISTS, f"File exists and overwrite is False: {path}")
            # OS-level check for existing file
            if not os.access(path, os.W_OK):
                 raise MCPError(ErrorCode.PERMISSION_DENIED, f"OS-level write permission denied for existing file: {path}")

        try:
            with open(path, 'w', encoding='utf-8') as f:
                bytes_written = f.write(content)
            logger.info(f"Successfully wrote {bytes_written} bytes to '{path}'")
            return OperationResult(success=True, data={"bytes_written": bytes_written, "path": str(file_path.absolute())})
        except Exception as e:
            logger.error(f"Error writing to file '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to write to file '{path}': {str(e)}") from e

class DeleteFile(Operation):
    name = "delete_file"
    description = "Deletes a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file to delete")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path = args.path
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing delete_file: path='{path}', agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")

        # --- Permission Check ---
        if not check_file_permission(path, "delete", file_perm_rules):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent does not have 'delete' permission for path prefix related to: {path}")
        # --- ---

        file_path = Path(path)

        if not file_path.exists():
            # Idempotency: If file already doesn't exist, maybe return success? Or specific error?
            # Let's stick to RESOURCE_NOT_FOUND for clarity.
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File or directory not found: {path}")
        if file_path.is_dir():
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is a directory, not a file: {path}.")

        parent_dir = file_path.parent
        # OS-level check
        if not os.access(parent_dir, os.W_OK):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"OS-level write permission denied for directory '{parent_dir}' needed to delete file.")

        try:
            os.remove(path)
            logger.info(f"Successfully deleted file: '{path}'")
            return OperationResult(success=True, data={"path": str(file_path.absolute())})
        except Exception as e:
            logger.error(f"Error deleting file '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to delete file '{path}': {str(e)}") from e

class ListDirectory(Operation):
    name = "list_directory"
    description = "Lists the contents of a specified directory."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=False, default=".", description="Directory path (default: current)"),
        ArgumentDefinition(name="show_hidden", type="boolean", required=False, default=False, description="Include hidden files/dirs (starting with '.')"),
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        path = args.path
        show_hidden = args.show_hidden
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []

        logger.debug(f"Executing list_directory: path='{path}', show_hidden={show_hidden}, agent='{agent_permissions.get('agent_id', 'default') if agent_permissions else 'default'}'")

        # --- Permission Check ---
        # Need 'list' permission for the directory itself
        if not check_file_permission(path, "list", file_perm_rules):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent does not have 'list' permission for directory: {path}")
        # --- ---

        dir_path = Path(path)

        if not dir_path.exists():
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Directory not found: {path}")
        if not dir_path.is_dir():
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a directory: {path}")
        # OS-level check
        if not os.access(path, os.R_OK):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"OS-level read permission denied for directory: {path}")

        try:
            items = []
            for item_name in os.listdir(path):
                if not show_hidden and item_name.startswith('.'):
                    continue
                # Check if agent has permission to even *list* this specific item's existence?
                # For simplicity, the current check_file_permission only checks the top dir.
                # A more granular system might check each item_path here.
                item_path_str = os.path.join(path, item_name)
                try:
                     # Use stat to check type without following symlinks if needed (lstat)
                     is_dir = os.path.isdir(item_path_str)
                     item_type = "directory" if is_dir else "file"
                except OSError:
                     item_type = "unknown/inaccessible" # Handle potential broken links etc.

                items.append({"name": item_name, "type": item_type})

            items.sort(key=lambda x: (x['type'] != 'directory', x['name'].lower()))

            logger.debug(f"list_directory successful for '{path}'")
            return OperationResult(success=True, data={"path": str(dir_path.absolute()), "contents": items})
        except Exception as e:
            logger.error(f"Error listing directory '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to list directory '{path}': {str(e)}") from e
