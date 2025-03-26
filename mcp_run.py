#!/usr/bin/env python3
import os
import sys
import uvicorn
import logging

# Add project root to path to allow running `python mcp_run.py` from root
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Configure logging BEFORE loading other modules that might log
log_level_name = os.getenv("MCP_LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=log_level_name,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# --- Main Execution ---
if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "127.0.0.1") # Default to localhost for security
    port = int(os.getenv("MCP_PORT", "8000"))
    # Allow uvicorn to handle log level based on env var or its defaults
    reload_server = os.getenv("MCP_RELOAD", "false").lower() == "true"

    logger.info(f"Starting MCP Server on http://{host}:{port}")
    if reload_server:
        logger.warning("Server reload enabled (development mode).")

    try:
        # Point uvicorn to the FastAPI app instance within the MCP package
        # Use "app_module:app_instance" syntax
        uvicorn.run("MCP.server:app",
                    host=host,
                    port=port,
                    log_level=log_level_name.lower(), # Pass log level to uvicorn
                    reload=reload_server,
                    # Optionally add reload_dirs if reload=True
                    # reload_dirs=[os.path.join(root_dir, "MCP")]
                    )
    except ImportError as e:
         # Check if it's the specific app import failing
         if "MCP.server" in str(e):
              logger.error(f"Could not import MCP server application 'MCP.server:app'. "
                           f"Ensure MCP/server.py exists and contains 'app = FastAPI()'. Error: {e}")
         else:
              logger.error(f"An import error occurred: {e}", exc_info=True)
         sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}", exc_info=True)
        sys.exit(1)
