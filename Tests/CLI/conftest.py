import pytest
import sys
from pathlib import Path
import logging

# --- Project Setup ---
# Ensure project module is importable by adding project root to sys.path
# Assumes conftest.py is in Tests/CLI/
root_dir = Path(__file__).parent.parent.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
# --- End Project Setup ---

logger = logging.getLogger(__name__)

# --- Fixtures ---
@pytest.fixture(scope="module")
def project_root():
    """Return the project root directory as a Path object."""
    return root_dir