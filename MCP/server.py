import logging
from fastapi import FastAPI, Request, status # Removed HTTPException as we use JSONResponse directly
from fastapi.responses import JSONResponse
from pydantic import ValidationError

try:
    from .models import MCPRequest, MCPSuccessResponse, MCPErrorResponse, MCPResponse
    from .registry import operation_registry
    from .errors import MCPError, ErrorCode, DEFAULT_MESSAGES
    from .operations.base import OperationResult
    from .permissions import get_agent_permissions
except ImportError:
    from models import MCPRequest, MCPSuccessResponse, MCPErrorResponse, MCPResponse
    from registry import operation_registry
    from errors import MCPError, ErrorCode, DEFAULT_MESSAGES
    from operations.base import OperationResult
    from permissions import get_agent_permissions


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MCP Operation Server",
    description="Exposes registered operations via the Multifaceted Capability Protocol.",
    version="1.0.0",
)

@app.on_event("startup")
async def startup_event():
    # Discover operations when the server starts
    operation_registry.discover_operations()
    logger.info("MCP Server started.")
    logger.info(f"Available operations: {list(operation_registry.get_all().keys())}")

@app.post("/mcp",
           response_model=None, # We manually create JSON responses based on success/error
           summary="Handle MCP Requests",
           tags=["MCP"])
async def handle_mcp_request(request: MCPRequest):
    """
    Receives an MCP request, checks permissions, validates arguments,
    executes the operation, and returns an MCP response.
    """
    # Use request ID in logs for better tracking
    log_prefix = f"[Req ID: {request.id}] "
    logger.info(f"{log_prefix}Received: Operation='{request.operation}', Agent='{request.agent_id}', Args={request.arguments}")

    # --- Permission Check ---
    agent_perms = get_agent_permissions(request.agent_id)
    requested_op_name = request.operation

    allowed_ops = agent_perms.get('allowed_operations', [])
    is_op_allowed = "*" in allowed_ops or requested_op_name in allowed_ops

    if not is_op_allowed:
        logger.warning(f"{log_prefix}Permission denied for agent '{request.agent_id}' to run operation '{requested_op_name}'.")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.PERMISSION_DENIED,
            message=f"Agent '{request.agent_id}' does not have permission to execute operation '{requested_op_name}'."
        )
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content=error_resp.dict())
    # --- End Permission Check ---

    # 1. Find Operation
    operation = operation_registry.get(requested_op_name)
    if not operation:
        logger.warning(f"{log_prefix}Operation '{requested_op_name}' not found.")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.OPERATION_NOT_FOUND,
            message=f"Operation '{requested_op_name}' not found."
        )
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp.dict())

    # 2. Validate Arguments
    try:
        ArgumentModel = operation.get_argument_model()
        # Pydantic automatically ignores extra fields by default, which is usually desired.
        validated_args = ArgumentModel(**request.arguments)
        logger.debug(f"{log_prefix}Validated arguments for '{requested_op_name}': {validated_args.dict()}")
    except ValidationError as e:
        logger.warning(f"{log_prefix}Argument validation failed for '{requested_op_name}': {e}")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.VALIDATION_ERROR,
            message=f"Argument validation failed: {str(e)}" # Provide Pydantic error details
        )
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp.dict())
    except Exception as e: # Catch errors during model creation or other validation prep
         logger.error(f"{log_prefix}Error preparing arguments for '{requested_op_name}': {e}", exc_info=True)
         error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.INVALID_ARGUMENTS, # Or maybe UNKNOWN_ERROR
            message=f"Internal error processing arguments: {str(e)}"
         )
         return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

    # 3. Execute Operation
    try:
        # Pass the agent's full permission context to the execute method
        result: OperationResult = operation.execute(validated_args, agent_perms)

        if result.success:
            logger.info(f"{log_prefix}Operation '{requested_op_name}' executed successfully.")
            success_resp = MCPSuccessResponse(id=request.id, result=result.data)
            return JSONResponse(status_code=status.HTTP_200_OK, content=success_resp.dict())
        else:
            # This path implies the operation handled the error internally but didn't raise MCPError
            # It returned OperationResult(success=False). We should encourage raising MCPError.
            logger.error(f"{log_prefix}Operation '{requested_op_name}' returned failure: {result.message}")
            # Use OPERATION_FAILED as a generic code if the operation didn't specify one implicitly
            err_code = ErrorCode.OPERATION_FAILED
            error_resp = MCPErrorResponse(
                id=request.id,
                error_code=int(err_code), # Ensure it's an int
                message=result.message or DEFAULT_MESSAGES.get(err_code)
            )
            # Treat non-exception failures as internal server errors unless specified otherwise
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

    except MCPError as e:
        # Handle controlled errors raised explicitly by operations
        logger.warning(f"{log_prefix}Operation '{requested_op_name}' raised MCPError: Code={e.code}, Msg='{e.message}'")
        error_resp = MCPErrorResponse(id=request.id, error_code=int(e.code), message=e.message)
        http_status = map_error_code_to_http_status(e.code)
        return JSONResponse(status_code=http_status, content=error_resp.dict())
    except Exception as e:
        # Handle unexpected errors during execution
        logger.exception(f"{log_prefix}Unexpected error executing '{requested_op_name}': {e}")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.UNKNOWN_ERROR,
            message=f"An unexpected internal server error occurred during operation execution: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

def map_error_code_to_http_status(error_code: ErrorCode) -> int:
    """Maps internal ErrorCodes enum to suitable HTTP status codes."""
    ec = ErrorCode(error_code) # Ensure we have the enum member
    if ec == ErrorCode.SUCCESS: return status.HTTP_200_OK
    elif ec == ErrorCode.OPERATION_NOT_FOUND or ec == ErrorCode.RESOURCE_NOT_FOUND: return status.HTTP_404_NOT_FOUND
    elif ec in [ErrorCode.INVALID_ARGUMENTS, ErrorCode.VALIDATION_ERROR, ErrorCode.INVALID_REQUEST]: return status.HTTP_400_BAD_REQUEST
    elif ec == ErrorCode.PERMISSION_DENIED or ec == ErrorCode.OS_PERMISSION_DENIED: return status.HTTP_403_FORBIDDEN
    elif ec == ErrorCode.RESOURCE_EXISTS: return status.HTTP_409_CONFLICT
    elif ec == ErrorCode.RESOURCE_BUSY: return status.HTTP_503_SERVICE_UNAVAILABLE
    elif ec == ErrorCode.TIMEOUT: return status.HTTP_504_GATEWAY_TIMEOUT
    else: return status.HTTP_500_INTERNAL_SERVER_ERROR
