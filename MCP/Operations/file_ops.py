import os
import logging
from pathlib import Path
from typing import Optional, List # Added List for list_directory
from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# --- ReadFile (from previous step) ---
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
        content_lines = [] # Define outside try block

        logger.debug(f"Executing read_file: path='{path}', lines={lines_to_read}")

        if not os.path.exists(path):
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File not found: {path}")
        if not os.path.isfile(path):
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a file: {path}")
        if not os.access(path, os.R_OK):
            raise MCPError(ErrorCode.PERMISSION_DENIED, f"No read permission for file: {path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                if lines_to_read is not None and lines_to_read > 0:
                    try:
                        # Read line by line to handle large files better
                        for _ in range(lines_to_read):
                             line = next(f)
                             content_lines.append(line.rstrip('\n'))
                    except StopIteration:
                         # Reached EOF before reading requested number of lines, which is fine
                         pass
                    content = "\n".join(content_lines)
                else:
                    content = f.read()
            logger.debug(f"read_file successful for '{path}'")
            return CapabilityResult(success=True, data={"content": content})
        except UnicodeDecodeError as e:
            logger.warning(f"UnicodeDecodeError reading file '{path}': {e}")
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Cannot decode file '{path}' as UTF-8 text.") from e
        except Exception as e:
            logger.error(f"Error reading file '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to read file '{path}': {str(e)}") from e
        return OperationResult(success=True, data={"content": content})

class WriteFile(Capability):
    name = "write_file"
    description = "Writes content to a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file"),
        ArgumentDefinition(name="content", type="string", required=True, description="Content to write"),
        ArgumentDefinition(name="overwrite", type="boolean", required=False, default=False, description="Overwrite if file exists (default: False)")
    ]

    def execute(self, args: BaseModel) -> CapabilityResult:
        path = args.path
        content = args.content
        overwrite = args.overwrite

        logger.debug(f"Executing write_file: path='{path}', overwrite={overwrite}")

        file_path = Path(path)
        dir_path = file_path.parent

        if not dir_path.exists():
             raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Directory does not exist: {dir_path}")
        if not dir_path.is_dir():
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Parent path is not a directory: {dir_path}")
        if not os.access(dir_path, os.W_OK):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"No write permission in directory: {dir_path}")

        if file_path.exists():
            if file_path.is_dir():
                 raise MCPError(ErrorCode.RESOURCE_EXISTS, f"Path exists and is a directory: {path}")
            if not overwrite:
                 raise MCPError(ErrorCode.RESOURCE_EXISTS, f"File exists and overwrite is False: {path}")
            if not os.access(path, os.W_OK):
                 raise MCPError(ErrorCode.PERMISSION_DENIED, f"No write permission for existing file: {path}")

        try:
            with open(path, 'w', encoding='utf-8') as f:
                bytes_written = f.write(content)
            logger.info(f"Successfully wrote {bytes_written} bytes to '{path}'")
            return CapabilityResult(success=True, data={"bytes_written": bytes_written, "path": path})
        except Exception as e:
            logger.error(f"Error writing to file '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to write to file '{path}': {str(e)}") from e

# --- DeleteFile ---
class DeleteFile(Capability):
    name = "delete_file"
    description = "Deletes a specified file."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=True, description="Path to the file to delete")
        # Maybe add 'force' later if needed for non-empty dirs etc.
    ]

    def execute(self, args: BaseModel) -> CapabilityResult:
        path = args.path
        logger.debug(f"Executing delete_file: path='{path}'")

        file_path = Path(path)

        if not file_path.exists():
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"File or directory not found: {path}")
        if file_path.is_dir():
             # Decide if deleting directories is allowed/intended. For now, restrict to files.
             raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is a directory, not a file: {path}. Use a different capability for directories.")

        parent_dir = file_path.parent
        if not os.access(parent_dir, os.W_OK): # Need write permission in parent dir to delete
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"No write permission in directory '{parent_dir}' to delete file.")

        try:
            os.remove(path)
            logger.info(f"Successfully deleted file: '{path}'")
            return CapabilityResult(success=True, data={"path": path})
        except Exception as e:
            logger.error(f"Error deleting file '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to delete file '{path}': {str(e)}") from e

# --- ListDirectory ---
class ListDirectory(Capability):
    name = "list_directory"
    description = "Lists the contents of a specified directory."
    arguments = [
        ArgumentDefinition(name="path", type="string", required=False, default=".", description="Directory path (default: current)"),
        ArgumentDefinition(name="show_hidden", type="boolean", required=False, default=False, description="Include hidden files/dirs (starting with '.')"),
        # Add recursive, long_format etc. if needed later
    ]

    def execute(self, args: BaseModel) -> CapabilityResult:
        path = args.path
        show_hidden = args.show_hidden
        logger.debug(f"Executing list_directory: path='{path}', show_hidden={show_hidden}")

        dir_path = Path(path)

        if not dir_path.exists():
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Directory not found: {path}")
        if not dir_path.is_dir():
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Path is not a directory: {path}")
        if not os.access(path, os.R_OK):
             raise MCPError(ErrorCode.PERMISSION_DENIED, f"No read permission for directory: {path}")

        try:
            items = []
            for item in os.listdir(path):
                if not show_hidden and item.startswith('.'):
                    continue
                item_path = os.path.join(path, item)
                item_type = "directory" if os.path.isdir(item_path) else "file"
                items.append({"name": item, "type": item_type})

            # Sort items alpha, directories first perhaps?
            items.sort(key=lambda x: (x['type'] != 'directory', x['name']))

            logger.debug(f"list_directory successful for '{path}'")
            return CapabilityResult(success=True, data={"path": os.path.abspath(path), "contents": items})
        except Exception as e:
            logger.error(f"Error listing directory '{path}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to list directory '{path}': {str(e)}") from e
