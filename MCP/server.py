import logging
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError # Import for specific validation errors

# Assuming MCP components are in the same directory or sys.path is set correctly
from .models import MCPRequest, MCPSuccessResponse, MCPErrorResponse, MCPResponse
from .registry import capability_registry # Use the initialized singleton
from .errors import MCPError, ErrorCode, DEFAULT_MESSAGES
from .capabilities.base import CapabilityResult # Import CapabilityResult

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MCP Capability Server",
    description="Exposes registered capabilities via the Multifaceted Capability Protocol.",
    version="1.0.0",
)

@app.on_event("startup")
async def startup_event():
    # Discover capabilities when the server starts
    capability_registry.discover_capabilities()
    logger.info("MCP Server started.")
    logger.info(f"Available capabilities: {list(capability_registry.get_all().keys())}")

@app.post("/mcp",
           # response_model=MCPResponse, # Using Union for docs, but manually creating JSON
           summary="Handle MCP Requests",
           tags=["MCP"])
async def handle_mcp_request(request: MCPRequest):
    """
    Receives an MCP request, validates arguments, executes the capability,
    and returns an MCP response.
    """
    logger.info(f"Received MCP request (ID: {request.id}): Capability='{request.capability}' Args={request.arguments}")

    # 1. Find Capability
    capability = capability_registry.get(request.capability)
    if not capability:
        logger.warning(f"Capability '{request.capability}' not found (ID: {request.id}).")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.CAPABILITY_NOT_FOUND,
            message=f"Capability '{request.capability}' not found."
        )
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content=error_resp.dict())

    # 2. Validate Arguments using dynamic Pydantic model
    try:
        ArgumentModel = capability.get_argument_model()
        validated_args = ArgumentModel(**request.arguments) # Validate dict against the model
        logger.debug(f"Validated arguments for '{request.capability}': {validated_args.dict()}")
    except ValidationError as e:
        logger.warning(f"Argument validation failed for '{request.capability}' (ID: {request.id}): {e}")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.VALIDATION_ERROR,
            message=f"Argument validation failed: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content=error_resp.dict())
    except Exception as e: # Catch errors during model creation perhaps
         logger.error(f"Error preparing arguments for '{request.capability}' (ID: {request.id}): {e}")
         error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.INVALID_ARGUMENTS,
            message=f"Internal error processing arguments: {str(e)}"
         )
         return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())


    # 3. Execute Capability
    try:
        result: CapabilityResult = capability.execute(validated_args) # Pass validated model

        if result.success:
            logger.info(f"Capability '{request.capability}' executed successfully (ID: {request.id}).")
            success_resp = MCPSuccessResponse(
                id=request.id,
                result=result.data # Use the data field from CapabilityResult
            )
            return JSONResponse(status_code=status.HTTP_200_OK, content=success_resp.dict())
        else:
            # This path might not be reached if capabilities raise MCPError on failure
            logger.error(f"Capability '{request.capability}' returned failure (ID: {request.id}): {result.message}")
            err_code = ErrorCode.OPERATION_FAILED # Default if capability doesn't provide code
            error_resp = MCPErrorResponse(
                id=request.id,
                error_code=err_code,
                message=result.message or DEFAULT_MESSAGES.get(err_code)
            )
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())

    except MCPError as e:
        # Handle controlled errors raised by capabilities
        logger.warning(f"Capability '{request.capability}' raised MCPError (ID: {request.id}): Code={e.code}, Msg='{e.message}'")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=e.code,
            message=e.message
        )
        http_status = map_error_code_to_http_status(e.code)
        return JSONResponse(status_code=http_status, content=error_resp.dict())

    except Exception as e:
        # Handle unexpected errors during execution
        logger.exception(f"Unexpected error executing '{request.capability}' (ID: {request.id}): {e}")
        error_resp = MCPErrorResponse(
            id=request.id,
            error_code=ErrorCode.UNKNOWN_ERROR,
            message=f"An unexpected internal error occurred during capability execution: {str(e)}"
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=error_resp.dict())


def map_error_code_to_http_status(error_code: int) -> int:
    """Maps internal ErrorCodes to suitable HTTP status codes."""
    # (Same mapping function as in the previous response)
    if error_code == ErrorCode.SUCCESS: return status.HTTP_200_OK
    elif error_code == ErrorCode.CAPABILITY_NOT_FOUND or error_code == ErrorCode.RESOURCE_NOT_FOUND: return status.HTTP_404_NOT_FOUND
    elif error_code in [ErrorCode.INVALID_ARGUMENTS, ErrorCode.VALIDATION_ERROR, ErrorCode.INVALID_REQUEST]: return status.HTTP_400_BAD_REQUEST
    elif error_code == ErrorCode.PERMISSION_DENIED: return status.HTTP_403_FORBIDDEN
    elif error_code == ErrorCode.RESOURCE_EXISTS: return status.HTTP_409_CONFLICT
    elif error_code == ErrorCode.RESOURCE_BUSY: return status.HTTP_503_SERVICE_UNAVAILABLE
    else: return status.HTTP_500_INTERNAL_SERVER_ERROR
