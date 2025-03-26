import logging
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

# UPDATED imports
from .models import MCPRequest, MCPSuccessResponse, MCPErrorResponse, MCPResponse
from .registry import operation_registry # RENAMED
from .errors import MCPError, ErrorCode, DEFAULT_MESSAGES
from .operations.base import OperationResult # RENAMED
from .permissions import get_agent_permissions # ADDED for Phase 2

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MCP Operation Server", # RENAMED
    description="Exposes registered operations via the Multifaceted Capability Protocol.", # RENAMED
    version="1.0.0",
)

@app.on_event("startup")
async def startup_event():
    operation_registry.discover_operations() # RENAMED
    logger.info("MCP Server started.")
    logger.info(f"Available operations: {list(operation_registry.get_all().keys())}") # RENAMED

@app.post("/mcp", tags=["MCP"])
async def handle_mcp_request(request: MCPRequest):
    """
    Receives an MCP request, checks permissions, validates arguments,
    executes the operation, and returns an MCP response.
    """
    logger.info(f"Received MCP request (ID: {request.id}): Operation='{request.operation}' Agent='{request.agent_id}' Args={request.arguments}") # RENAMED, ADDED Agent

    # --- Phase 2: Permission Check ---
    agent_perms = get_agent_permissions(request.agent_id)
    requested_op_name = request.operation

    allowed_ops = agent_perms.get('allowed_operations', [])
    is_allowed = "*" in allowed_ops or requested_op_name in allowed_ops

    if not is_allowed:
        logger.warning(f"Permission denied for agent '{request.agent_id}' to run operation '{requested_op_name}' (ID: {request.id}).")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.PERMISSION_DENIED,
            message=f"Agent '{request.agent_id}' does not have permission to execute operation '{requested_op_name}'."
        )
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=error_resp.dict())
    # --- End Phase 2 ---

    # 1. Find Operation
    operation = operation_registry.get(requested_op_name) # Use validated name
    if not operation:
        logger.warning(f"Operation '{requested_op_name}' not found (ID: {request.id}).") # RENAMED
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.OPERATION_NOT_FOUND, # Use updated code
            message=f"Operation '{requested_op_name}' not found." # RENAMED
        )
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp.dict())

    # 2. Validate Arguments
    try:
        ArgumentModel = operation.get_argument_model()
        validated_args = ArgumentModel(**request.arguments)
        logger.debug(f"Validated arguments for '{requested_op_name}': {validated_args.dict()}")
    except ValidationError as e:
        logger.warning(f"Argument validation failed for '{requested_op_name}' (ID: {request.id}): {e}")
        error_resp = MCPErrorResponse(
            id=request.id, error_code=ErrorCode.VALIDATION_ERROR, message=f"Argument validation failed: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp.dict())
    except Exception as e:
         logger.error(f"Error preparing arguments for '{requested_op_name}' (ID: {request.id}): {e}")
         error_resp = MCPErrorResponse(
            id=request.id, error_code=ErrorCode.INVALID_ARGUMENTS, message=f"Internal error processing arguments: {str(e)}"
         )
         return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

    # 3. Execute Operation
    try:
        # --- Pass agent permissions to execute method --- (Phase 2)
        agent_file_perms = agent_perms.get('file_permissions', [])
        permissions_context = {'file': agent_file_perms}
        # --- ---
        result: OperationResult = operation.execute(validated_args, permissions_context) # Pass permissions

        if result.success:
            logger.info(f"Operation '{requested_op_name}' executed successfully (ID: {request.id}).")
            success_resp = MCPSuccessResponse(id=request.id, result=result.data)
            return JSONResponse(status_code=status.HTTP_200_OK, content=success_resp.dict())
        else:
            # Should ideally be handled by MCPError exception below, but include as fallback
            logger.error(f"Operation '{requested_op_name}' returned failure (ID: {request.id}): {result.message}")
            err_code = ErrorCode.OPERATION_FAILED
            error_resp = MCPErrorResponse(
                id=request.id, error_code=err_code, message=result.message or DEFAULT_MESSAGES.get(err_code)
            )
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

    except MCPError as e:
        logger.warning(f"Operation '{requested_op_name}' raised MCPError (ID: {request.id}): Code={e.code}, Msg='{e.message}'")
        error_resp = MCPErrorResponse(id=request.id, error_code=e.code, message=e.message)
        http_status = map_error_code_to_http_status(e.code)
        return JSONResponse(status_code=http_status, content=error_resp.dict())
    except Exception as e:
        logger.exception(f"Unexpected error executing '{requested_op_name}' (ID: {request.id}): {e}")
        error_resp = MCPErrorResponse(
            id=request.id, error_code=ErrorCode.UNKNOWN_ERROR,
            message=f"An unexpected internal error occurred during operation execution: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

def map_error_code_to_http_status(error_code: int) -> int:
    """Maps internal ErrorCodes to suitable HTTP status codes."""
    if error_code == ErrorCode.SUCCESS: return status.HTTP_200_OK
    elif error_code == ErrorCode.OPERATION_NOT_FOUND or error_code == ErrorCode.RESOURCE_NOT_FOUND: return status.HTTP_404_NOT_FOUND
    elif error_code in [ErrorCode.INVALID_ARGUMENTS, ErrorCode.VALIDATION_ERROR, ErrorCode.INVALID_REQUEST]: return status.HTTP_400_BAD_REQUEST
    elif error_code == ErrorCode.PERMISSION_DENIED: return status.HTTP_403_FORBIDDEN # Use 403 for permission issues
    elif error_code == ErrorCode.RESOURCE_EXISTS: return status.HTTP_409_CONFLICT
    elif error_code == ErrorCode.RESOURCE_BUSY: return status.HTTP_503_SERVICE_UNAVAILABLE
    else: return status.HTTP_500_INTERNAL_SERVER_ERROR
