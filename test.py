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
    Looks for any 'Tests' folder recursively.
    """
    # We use pytest with arguments:
    #   --maxfail=1   Stop after first failing test
    #   -v            Verbose output
    #   --asyncio     Enable pytest-asyncio
    #
    # The blank argument array uses the current directory as root by default.
    #
    # Adjust or add arguments as you like:
    args = [
        "--maxfail=1",
        "-v",
        "--asyncio"
    ]
    sys.exit(pytest.main(args))

if __name__ == "__main__":
    main()
