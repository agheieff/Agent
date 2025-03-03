
"""
test.py

Runs all tests (located in any 'Tests/' subdirectory at any level).
"""

import sys
import pytest

def main():








    args = [
        "--maxfail=1",
        "-v",
        "--asyncio"
    ]
    sys.exit(pytest.main(args))

if __name__ == "__main__":
    main()
