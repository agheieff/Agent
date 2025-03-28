# File: /Tests/conftest.py

import sys
import os
from pathlib import Path
import logging

# Configure logging specifically for this file if needed, or rely on root config
# Ensure logging is configured *before* first use if not already done.
# Basic config example:
# logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__) # Use __name__ for logger

# Calculate the project root directory (assuming this file is in /path/to/project/Tests/)
project_root = Path(__file__).parent.parent.resolve()

# Add project root to sys.path if it's not already there
if str(project_root) not in sys.path:
    # --- Add print statement for debugging ---
    print(f"DEBUG [Tests/conftest.py]: Adding project root to sys.path: {project_root}", file=sys.stderr)
    # --- End print statement ---
    logger.debug(f"Adding project root to sys.path for testing: {project_root}")
    sys.path.insert(0, str(project_root))
else:
    # --- Add print statement for debugging ---
    print(f"DEBUG [Tests/conftest.py]: Project root already in sys.path: {project_root}", file=sys.stderr)
    # --- End print statement ---
    logger.debug(f"Project root already in sys.path: {project_root}")

# Print sys.path right after modification for verification
print(f"DEBUG [Tests/conftest.py]: sys.path after modification: {sys.path}", file=sys.stderr)

# You can also define shared fixtures here if needed later
# import pytest
# @pytest.fixture(scope="session")
# def shared_resource():
#     print("Setting up shared resource")
#     yield "Resource Data"
#     print("Tearing down shared resource")
