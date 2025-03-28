# This file ensures the project root is added to the path
# for all tests discovered within the 'Tests' directory and its subdirectories.

import sys
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Calculate the project root directory (assuming this file is in /path/to/project/Tests/)
project_root = Path(__file__).parent.parent.resolve()

# Add project root to sys.path if it's not already there
if str(project_root) not in sys.path:
    logger.debug(f"Adding project root to sys.path for testing: {project_root}")
    sys.path.insert(0, str(project_root))
else:
    logger.debug(f"Project root already in sys.path: {project_root}")

# You can also define shared fixtures here if needed later
# Example:
# import pytest
# @pytest.fixture(scope="session")
# def shared_resource():
#     print("Setting up shared resource")
#     yield "Resource Data"
#     print("Tearing down shared resource")
