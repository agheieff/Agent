#!/usr/bin/env python

"""
Integration test for the ls feature with hidden files
"""

import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Tools.Search.search_tools import SearchTools

async def test_ls_feature():
    """Test the ls feature with hidden files"""
    print("\n=== Testing LS feature with hidden files ===")

    # Create a test directory with hidden files
    test_dir = Path(__file__).parent.parent / "temp" / "ls_test"
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create some test files
    (test_dir / "file1.txt").touch()
    (test_dir / "file2.txt").touch()
    (test_dir / ".hidden1").touch()
    (test_dir / ".hidden2").touch()

    # Create SearchTools instance
    search_tools = SearchTools()

    try:
        # Test with default (showing hidden files)
        print("\nTest 1: Default behavior (show hidden)")
        result = search_tools.ls(str(test_dir))
        print(f"Files: {[f['name'] for f in result.get('files', [])]}")
        print(f"Total entries: {len(result.get('entries', []))}")
        print(f"Hidden entries count: {sum(1 for e in result.get('entries', []) if e.get('is_hidden', False))}")

        # Verify expected results
        entries = result.get('entries', [])
        assert len(entries) == 4, f"Expected 4 entries, got {len(entries)}"
        hidden_count = sum(1 for e in entries if e.get('is_hidden', False))
        assert hidden_count == 2, f"Expected 2 hidden entries, got {hidden_count}"

        # Test with hiding hidden files
        print("\nTest 2: With hide_hidden=True")
        result = search_tools.ls(str(test_dir), hide_hidden=True)
        print(f"Files: {[f['name'] for f in result.get('files', [])]}")
        print(f"Total entries: {len(result.get('entries', []))}")
        print(f"Hidden entries count: {sum(1 for e in result.get('entries', []) if e.get('is_hidden', False))}")

        # Verify expected results
        entries = result.get('entries', [])
        assert len(entries) == 2, f"Expected 2 entries with hidden files filtered, got {len(entries)}"

        print("\n✅ LS feature test passed")
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        # Cleanup
        for file in test_dir.glob("*"):
            file.unlink()
        for file in test_dir.glob(".*"):
            if file.name not in [".", ".."]:
                file.unlink()
        test_dir.rmdir()

if __name__ == "__main__":
    result = asyncio.run(test_ls_feature())
    sys.exit(0 if result else 1)