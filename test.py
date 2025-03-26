#!/usr/bin/env python3
"""
Test runner script. Uses pytest if available, otherwise falls back to unittest.
Run this from the project root directory: python test.py
"""
import sys
import os
import logging

# --- Setup Project Path ---
# Ensure the project root directory is in sys.path for imports
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
# Optionally set PYTHONPATH environment variable as well
# os.environ['PYTHONPATH'] = root_dir + os.pathsep + os.environ.get('PYTHONPATH', '')
# --- End Setup ---

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def run_tests():
    """Discovers and runs tests using pytest or unittest."""
    test_dir = "Tests" # Directory containing tests relative to root_dir

    if not os.path.isdir(test_dir):
         logger.error(f"Test directory '{test_dir}' not found in project root '{root_dir}'.")
         return 1

    logger.info(f"Running tests from directory: {os.path.join(root_dir, test_dir)}")

    # --- Use Pytest if available ---
    try:
        import pytest
        logger.info("Using pytest to run tests...")
        # Run pytest discovery starting from the specified test directory
        # -v for verbose, add other options as needed (e.g., '-s' for stdout)
        args = ['-v', test_dir]
        exit_code = pytest.main(args)
        return exit_code
    except ImportError:
        logger.warning("pytest not found, falling back to unittest.")
    except Exception as e:
        logger.error(f"An error occurred while trying to run pytest: {e}")
        # Fallback or exit
        logger.warning("Falling back to unittest due to pytest error.")

    # --- Fallback to Unittest ---
    try:
        import unittest
        logger.info("Using unittest to discover and run tests...")
        loader = unittest.TestLoader()
        # Discover tests in the specified directory, looking for files matching 'test_*.py'
        suite = loader.discover(test_dir, pattern='test_*.py', top_level_dir=root_dir)

        if suite.countTestCases() == 0:
             logger.warning(f"No unittest tests found in '{test_dir}'.")
             return 0 # No tests found isn't necessarily an error

        runner = unittest.TextTestRunner(verbosity=2) # Higher verbosity
        result = runner.run(suite)

        # Return 0 for success, 1 for failure
        return 0 if result.wasSuccessful() else 1
    except ImportError:
        logger.error("Neither pytest nor unittest seem to be available.")
        return 1
    except Exception as e:
        logger.error(f"An error occurred while trying to run unittest: {e}", exc_info=True)
        return 1


# --- Main Execution ---
if __name__ == '__main__':
    logger.info("Starting test execution...")
    exit_code = run_tests()
    logger.info(f"Test execution finished with exit code: {exit_code}")
    sys.exit(exit_code)
