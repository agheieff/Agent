#!/usr/bin/env python3
import os
import sys
import uvicorn
import logging

# Ensure project root is in path if this script is at the root
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8000"))
    log_level = os.getenv("MCP_LOG_LEVEL", "info").lower()
    reload = os.getenv("MCP_RELOAD", "false").lower() == "true" # For development

    logger.info(f"Starting MCP Server on {host}:{port}")
    logger.info(f"Log level: {log_level}")
    if reload:
        logger.warning("Reload mode is enabled (for development).")

    try:
        # Point uvicorn to the FastAPI app instance inside MCP/server.py
        uvicorn.run("MCP.server:app",
                    host=host,
                    port=port,
                    log_level=log_level,
                    reload=reload)
    except ImportError as e:
         logger.error(f"Could not import MCP server application. Make sure MCP/server.py exists and contains 'app = FastAPI()'. Error: {e}")
    except Exception as e:
         logger.error(f"Failed to start MCP server: {e}", exc_info=True)
         sys.exit(1)
