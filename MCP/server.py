import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status as http_status
from fastapi.responses import JSONResponse
from pydantic import ValidationError

# Use relative imports within the MCP package
from .models import MCPRequest, MCPSuccessResponse, MCPErrorResponse, MCPResponse
from .registry import operation_registry
from .errors import MCPError, ErrorCode, DEFAULT_MESSAGES
from .Operations.base import OperationResult
from .permissions import get_agent_permissions

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Utility Functions ---

def map_error_code_to_http_status(error_code: ErrorCode) -> int:
    """Maps internal ErrorCodes enum to suitable HTTP status codes."""
    status_map = {
        ErrorCode.SUCCESS: http_status.HTTP_200_OK,
        ErrorCode.OPERATION_NOT_FOUND: http_status.HTTP_404_NOT_FOUND,
        ErrorCode.RESOURCE_NOT_FOUND: http_status.HTTP_404_NOT_FOUND,
        ErrorCode.INVALID_REQUEST: http_status.HTTP_400_BAD_REQUEST,
        ErrorCode.INVALID_ARGUMENTS: http_status.HTTP_400_BAD_REQUEST, # Or 422 if preferred
        ErrorCode.VALIDATION_ERROR: http_status.HTTP_400_BAD_REQUEST, # Or 422
        ErrorCode.PERMISSION_DENIED: http_status.HTTP_403_FORBIDDEN,
        ErrorCode.OS_PERMISSION_DENIED: http_status.HTTP_403_FORBIDDEN,
        ErrorCode.RESOURCE_EXISTS: http_status.HTTP_409_CONFLICT,
        ErrorCode.RESOURCE_BUSY: http_status.HTTP_503_SERVICE_UNAVAILABLE,
        ErrorCode.TIMEOUT: http_status.HTTP_504_GATEWAY_TIMEOUT,
        ErrorCode.NETWORK_ERROR: http_status.HTTP_502_BAD_GATEWAY, # Or 500/503
        ErrorCode.OPERATION_FAILED: http_status.HTTP_500_INTERNAL_SERVER_ERROR,
        ErrorCode.INVALID_OPERATION_STATE: http_status.HTTP_409_CONFLICT, # Or 500
        ErrorCode.UNKNOWN_ERROR: http_status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    # Ensure input is an ErrorCode member if possible
    try:
        ec = ErrorCode(error_code)
        return status_map.get(ec, http_status.HTTP_500_INTERNAL_SERVER_ERROR)
    except ValueError:
        logger.warning(f"Mapping unknown error code {error_code} to HTTP status 500")
        return http_status.HTTP_500_INTERNAL_SERVER_ERROR


# --- FastAPI Application Setup ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    # Startup: Discover operations
    operation_registry.discover_operations()
    logger.info("MCP Server started.")
    logger.info(f"Available operations: {list(operation_registry.get_all().keys())}")
    yield
    # Shutdown: (Add cleanup here if needed)
    logger.info("MCP Server shutting down.")

app = FastAPI(
    title="MCP Operation Server",
    description="Exposes registered MCP operations via a REST API.",
    version="1.0.0",
    lifespan=lifespan
)

# --- Exception Handlers ---

@app.exception_handler(MCPError)
async def mcp_exception_handler(request: Request, exc: MCPError):
    """Handles controlled MCP errors raised by operations."""
    request_id = getattr(request.state, "request_id", "unknown") # Get ID if set by middleware
    logger.warning(f"[Req ID: {request_id}] Handled MCPError: Code={exc.code}, Msg='{exc.message}'")
    http_code = map_error_code_to_http_status(exc.code)
    error_resp = MCPErrorResponse(
        id=request_id,
        error_code=int(exc.code),
        message=exc.message,
        details=exc.details
    )
    return JSONResponse(status_code=http_code, content=error_resp.model_dump())

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handles Pydantic validation errors during request parsing or argument validation."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(f"[Req ID: {request_id}] Argument validation failed: {exc.errors()}")
    error_resp = MCPErrorResponse(
        id=request_id,
        error_code=ErrorCode.VALIDATION_ERROR,
        message="Argument validation failed.",
        details=exc.errors() # Provide detailed Pydantic errors
    )
    # Use 400 for client-side validation errors
    return JSONResponse(status_code=http_status.HTTP_400_BAD_REQUEST, content=error_resp.model_dump())

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handles any other unexpected exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(f"[Req ID: {request_id}] Unexpected internal server error: {exc}") # Log full traceback
    error_resp = MCPErrorResponse(
        id=request_id,
        error_code=ErrorCode.UNKNOWN_ERROR,
        message=f"An unexpected internal server error occurred: {type(exc).__name__}",
        # Avoid leaking detailed internal error messages in production responses
        # details=str(exc) # Optionally include basic error string in details
    )
    return JSONResponse(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.model_dump())


# --- Middleware (Optional) ---
# Example: Add request ID to state for logging/handlers
@app.middleware("http")
async def add_request_id_middleware(request: Request, call_next):
    try:
         # Try to parse request body early if needed, be cautious of large bodies
         # For simplicity, just get ID from parsed MCPRequest later or generate one.
         # Here, we'll set a placeholder until the request body is parsed.
         request.state.request_id = "parsing..."
    except Exception:
         request.state.request_id = "invalid-request" # Handle cases where body parsing fails
    response = await call_next(request)
    return response


# --- API Endpoint ---

@app.post("/mcp",
          response_model=None, # Responses are created manually by handlers/endpoint
          summary="Handle MCP Requests",
          tags=["MCP"],
          responses={ # Define potential responses for OpenAPI documentation
              200: {"model": MCPSuccessResponse},
              400: {"model": MCPErrorResponse, "description": "Invalid Request/Validation Error"},
              403: {"model": MCPErrorResponse, "description": "Permission Denied"},
              404: {"model": MCPErrorResponse, "description": "Operation/Resource Not Found"},
              409: {"model": MCPErrorResponse, "description": "Conflict/Resource Exists"},
              500: {"model": MCPErrorResponse, "description": "Internal Server Error"},
          })
async def handle_mcp_request(request_body: MCPRequest, request: Request): # Inject request for state access
    """
    Receives an MCP request, validates permissions and arguments,
    executes the requested operation, and returns an MCP response.
    Error handling is primarily managed by exception handlers.
    """
    # Set request ID in state now that body is parsed
    request.state.request_id = request_body.id
    log_prefix = f"[Req ID: {request_body.id}] "
    logger.info(f"{log_prefix}Received: Op='{request_body.operation}', Agent='{request_body.agent_id}', Args={request_body.arguments}")

    # 1. Permission Check
    agent_perms = get_agent_permissions(request_body.agent_id)
    requested_op_name = request_body.operation
    allowed_ops = agent_perms.get('allowed_operations', [])
    is_op_allowed = "*" in allowed_ops or requested_op_name in allowed_ops

    if not is_op_allowed:
        raise MCPError(ErrorCode.PERMISSION_DENIED,
                       f"Agent '{request_body.agent_id}' lacks permission for operation '{requested_op_name}'.")

    # 2. Find Operation
    operation = operation_registry.get(requested_op_name)
    if not operation:
        raise MCPError(ErrorCode.OPERATION_NOT_FOUND, f"Operation '{requested_op_name}' not found.")

    # 3. Validate Arguments (using Pydantic's ValidationError handled by exception handler)
    ArgumentModel = operation.get_argument_model()
    validated_args = ArgumentModel(**request_body.arguments)
    logger.debug(f"{log_prefix}Validated args for '{requested_op_name}': {validated_args.model_dump()}")

    # 4. Execute Operation
    # MCPError and other Exceptions raised here will be caught by handlers
    result: OperationResult = operation.execute(validated_args, agent_perms)

    # 5. Handle Successful Execution (or explicit failure via OperationResult)
    if result.success:
        logger.info(f"{log_prefix}Operation '{requested_op_name}' executed successfully.")
        success_resp = MCPSuccessResponse(id=request_body.id, result=result.data)
        return JSONResponse(status_code=http_status.HTTP_200_OK, content=success_resp.model_dump())
    else:
        # If an operation returns success=False instead of raising MCPError
        logger.error(f"{log_prefix}Operation '{requested_op_name}' returned explicit failure: {result.message}")
        # Treat as a generic operation failure
        raise MCPError(ErrorCode.OPERATION_FAILED, result.message or DEFAULT_MESSAGES[ErrorCode.OPERATION_FAILED])
