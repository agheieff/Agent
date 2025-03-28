#!/usr/bin/env python3
"""
Test runner script.

Recommendation: Run tests directly using pytest from the project root:
    pytest -v

This script provides a fallback using `pytest.main` or `unittest`.
"""
import sys
import os
import logging
from pathlib import Path

# --- Setup Project Path ---
# Ensure the project root directory is in sys.path for imports *before* importing pytest/unittest
root_dir = Path(__file__).parent.resolve() # Use Path(__file__).parent as test.py is in root
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
        args = ['-v', test_dir] # Add '-s' if you want print statements during tests
        # Explicitly tell pytest where the root is, might help discovery
        # args.extend(['--rootdir', str(root_dir)]) # Optional, might help
        exit_code = pytest.main(args)
        return exit_code
    except ImportError:
        logger.warning("pytest not found. Cannot run tests with pytest.main().")
        return None # Indicate pytest wasn't found/run
    except Exception as e:
        logger.error(f"An error occurred while trying to run pytest: {e}", exc_info=True)
        return None # Indicate pytest failed unexpectedly


def run_tests_with_unittest():
    """Falls back to using unittest."""
    try:
        import unittest
        logger.info("Using unittest to discover and run tests...")
        test_dir = "Tests"
        loader = unittest.TestLoader()
        # Discover tests in the specified directory, looking for files matching 'test_*.py'
        suite = loader.discover(test_dir, pattern='test_*.py', top_level_dir=str(root_dir))

        if suite.countTestCases() == 0:
            logger.warning(f"No unittest tests found in '{test_dir}'.")
            return 0 # No tests found isn't necessarily an error

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        return 0 if result.wasSuccessful() else 1
    except ImportError:
        logger.error("unittest module not found (highly unlikely).")
        return 1
    except Exception as e:
        logger.error(f"An error occurred while trying to run unittest: {e}", exc_info=True)
        return 1

# --- Main Execution ---
if __name__ == '__main__':
    logger.info("Starting test execution...")
    logger.info("Recommendation: Run 'pytest -v' directly from the project root for best results.")

    # Try pytest first
    pytest_exit_code = run_tests_with_pytest()

    if pytest_exit_code is not None:
        # Pytest was found and executed (or failed during execution)
        exit_code = pytest_exit_code
    else:
        # Pytest wasn't found, try unittest
        logger.info("Falling back to unittest...")
        exit_code = run_tests_with_unittest()

    logger.info(f"Test execution finished with exit code: {exit_code}")
    sys.exit(exit_code)
