#!/usr/bin/env python3
import sys
import os
import logging
from pathlib import Path

# --- Setup Project Path ---
# Ensure the project root directory is in sys.path for imports
root_dir = Path(__file__).parent.resolve()
if str(root_dir) not in sys.path:
    print(f"DEBUG [test.py]: Adding project root to sys.path: {root_dir}", file=sys.stderr)
    sys.path.insert(0, str(root_dir))
else:
    print(f"DEBUG [test.py]: Project root already in sys.path: {root_dir}", file=sys.stderr)

print(f"DEBUG [test.py]: sys.path before running tests: {sys.path}", file=sys.stderr)
# --- End Setup ---


# Configure logging AFTER path setup, before running tests
log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=log_level_name, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def run_tests_with_pytest():
    """Attempts to run tests using pytest.main()."""
    try:
        import pytest
        logger.info("Using pytest via pytest.main()...")
        test_dir = "Tests"
        if not os.path.isdir(test_dir):
            logger.error(f"Test directory '{test_dir}' not found in project root '{root_dir}'.")
            return 1

        # Run pytest discovery starting from the specified test directory
        # Add '-s' if you want print statements during tests to be displayed
        args = ['-v', test_dir]
        exit_code = pytest.main(args)
        return exit_code
    except ImportError:
        logger.error("pytest not found. Please install it ('pip install pytest') to run tests.")
        return 1 # Indicate error
    except Exception as e:
        logger.error(f"An error occurred while trying to run pytest: {e}", exc_info=True)
        return 1 # Indicate error

# --- Main Execution ---
if __name__ == '__main__':
    logger.info("Starting test execution...")
    logger.info("Recommendation: Run 'pytest -v' directly from the project root.")

    exit_code = run_tests_with_pytest()

    logger.info(f"Test execution finished with exit code: {exit_code}")
    sys.exit(exit_code)
