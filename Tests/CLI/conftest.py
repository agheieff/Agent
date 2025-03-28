import pytest
import sys
from pathlib import Path
import logging

# --- Project Setup ---
# Path setup is handled by the top-level Tests/conftest.py
# --- End Project Setup ---

logger = logging.getLogger(__name__)

# --- Fixtures ---
@pytest.fixture(scope="module")
def project_root():
    """Return the project root directory as a Path object."""
    # Calculate the project root directory relative to this conftest file
    return Path(__file__).parent.parent.parent.resolve()

# Add other CLI-specific fixtures if needed
