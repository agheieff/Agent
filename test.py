#!/usr/bin/env python3
import unittest
import sys
import os

# Get the directory containing this script and add it to Python path
root_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, root_dir)

def run_tests():
    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = os.path.join(root_dir, 'Tests')
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    # Create a test runner with verbosity=2 for detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return 0 if tests passed, 1 if any failed
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    sys.exit(run_tests()) 