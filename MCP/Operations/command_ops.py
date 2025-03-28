import logging
import asyncio
import subprocess
import shlex # For safer command splitting
from pathlib import Path
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field

from .base import Operation, OperationResult, ArgumentDefinition
from ..errors import MCPError, ErrorCode
from ..permissions import check_file_permission # For checking working_directory if specified

logger = logging.getLogger(__name__)

# --- SECURITY WARNING ---
# Executing arbitrary commands is extremely dangerous.
# Ensure strict permissions are applied via MCP/permissions.py
# Only grant this operation to highly trusted agents or specific, limited commands.
# Consider running the MCP server in a sandboxed environment (e.g., Docker).
# Validate inputs carefully. Avoid shell=True in subprocess calls.
# --- END SECURITY WARNING ---

class ExecuteCommand(Operation):
    name = "execute_command"
    description = (
        "Executes a system command directly on the server where the MCP is running. "
        "SECURITY: This is a sensitive operation. Use with extreme caution."
    )
    arguments = [
        ArgumentDefinition(name="command", type="string", required=True, description="The command line to execute (e.g., 'ls -l /tmp'). Avoid complex shell syntax; provide direct command and arguments."),
        ArgumentDefinition(name="working_directory", type="string", required=False, default=None, description="Optional path to the directory where the command should be executed."),
        ArgumentDefinition(name="timeout", type="integer", required=False, default=60, description="Timeout in seconds before terminating the command (default: 60).")
    ]

    def execute(self, args: BaseModel, agent_permissions: Optional[Dict] = None) -> OperationResult:
        command_str = args.command
        working_dir = args.working_directory
        timeout = args.timeout if args.timeout and args.timeout > 0 else 60
        file_perm_rules = agent_permissions.get('file_permissions', []) if agent_permissions else []
        agent_id = agent_permissions.get('agent_id', 'unknown') if agent_permissions else 'unknown'

        logger.warning(f"[Agent: {agent_id}] Executing sensitive command: '{command_str}' (Timeout: {timeout}s, WD: {working_dir})")

        # --- Input Validation & Security Checks ---
        if not command_str:
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, "Command cannot be empty.")

        # Basic check for potentially dangerous shell metacharacters if we were using shell=True (which we avoid)
        # For safety, we'll split the command using shlex to handle arguments safely.
        try:
            # Split command string into a list suitable for subprocess without shell=True
            command_parts = shlex.split(command_str)
            if not command_parts:
                 raise ValueError("Command string resulted in empty command parts.")
        except ValueError as e:
            raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Invalid command string format: {e}")

        # Validate working directory if provided
        resolved_working_dir = None
        if working_dir:
            # Check agent permission to 'list' (as a proxy for 'access') the directory
            if not check_file_permission(working_dir, "list", file_perm_rules):
                 raise MCPError(ErrorCode.PERMISSION_DENIED, f"Agent lacks permission to access working directory: {working_dir}")
            try:
                # Resolve AFTER permission check
                resolved_working_dir = Path(working_dir).resolve(strict=True)
                if not resolved_working_dir.is_dir():
                    raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Working directory is not a valid directory: {working_dir}")
                logger.debug(f"Resolved working directory: {resolved_working_dir}")
            except FileNotFoundError:
                 raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Working directory not found: {working_dir}")
            except Exception as e:
                 raise MCPError(ErrorCode.INVALID_ARGUMENTS, f"Invalid working directory path '{working_dir}': {e}")

        # --- Execute Command ---
        try:
            # Use regular subprocess for synchronous execution
            process = subprocess.run(
                command_parts,  # Pass the split command parts
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=resolved_working_dir,  # Pass resolved path or None
                timeout=timeout,  # Set timeout
                check=False,  # Don't raise on non-zero exit
                text=True  # Return strings instead of bytes
            )

            # Access results directly - stdout/stderr are already strings
            return_code = process.returncode
            stdout = process.stdout.strip() if process.stdout else ""
            stderr = process.stderr.strip() if process.stderr else ""

            logger.info(f"Command '{command_str}' finished with code {return_code}. Stdout length: {len(stdout)}, Stderr length: {len(stderr)}")
            logger.debug(f"Stdout:\n{stdout}\nStderr:\n{stderr}")

            return OperationResult.success_result(data={
                "command_executed": command_str,
                "return_code": return_code,
                "stdout": stdout,
                "stderr": stderr,
            })

        except subprocess.TimeoutExpired:
            logger.error(f"Command '{command_str}' timed out after {timeout} seconds.")
            raise MCPError(ErrorCode.TIMEOUT, f"Command timed out after {timeout} seconds.") from None
            
        except FileNotFoundError:
            # This occurs if the primary command executable isn't found in PATH
            logger.error(f"Command not found: '{command_parts[0]}'")
            raise MCPError(ErrorCode.RESOURCE_NOT_FOUND, f"Command not found: '{command_parts[0]}'. Ensure it's in the system PATH.")
            
        except PermissionError as e:
            # OS-level permission error during execution
            logger.error(f"OS Permission denied executing command '{command_str}': {e}")
            raise MCPError(ErrorCode.OS_PERMISSION_DENIED, f"OS permission denied executing command: {e}") from e
            
        except Exception as e:
            logger.error(f"Error executing command '{command_str}': {e}", exc_info=True)
            raise MCPError(ErrorCode.OPERATION_FAILED, f"Failed to execute command: {str(e)}") from e
