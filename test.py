#!/usr/bin/env python
"""
test.py

Runs all tests (located in any 'Tests/' subdirectory at any level).
"""

import sys
import pytest

def main():
    """
    Discover and run all tests using Pytest.
    """
    args = [
        "--maxfail=1",  # Stop after first failing test
        "-v",           # Verbose output
    ]
    sys.exit(pytest.main(args))

if __name__ == "__main__":
    main()

