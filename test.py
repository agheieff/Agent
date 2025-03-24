#!/usr/bin/env python3
import unittest
import sys
import os

# Ensure we're running from the root directory of the project
root_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(root_dir)

# Explicitly add the project root to sys.path and set PYTHONPATH
os.environ['PYTHONPATH'] = root_dir
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

def run_tests():
    # Using pytest if available, otherwise fallback to unittest
    try:
        import pytest
        args = ['-v', 'Tests']
        return pytest.main(args)
    except ImportError:
        print("pytest not installed, falling back to unittest")
        loader = unittest.TestLoader()
        suite = loader.discover('Tests', pattern='test_*.py')
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(run_tests())
