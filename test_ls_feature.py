#\!/usr/bin/env python

"""
Test script for the updated ls feature
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent))

from Tools.Search.search_tools import SearchTools

async def test_ls_feature():
    """Test the ls feature with hidden files"""
    print("\n=== Testing LS feature with hidden files ===")
    
    # Create a test directory with hidden files
    test_dir = Path("test_ls_dir")
    test_dir.mkdir(exist_ok=True)
    
    # Create some test files
    (test_dir / "file1.txt").touch()
    (test_dir / "file2.txt").touch()
    (test_dir / ".hidden1").touch()
    (test_dir / ".hidden2").touch()
    
    # Create SearchTools instance
    search_tools = SearchTools()
    
    # Test with default (showing hidden files)
    print("\nTest 1: Default behavior (show hidden)")
    result = search_tools.ls(str(test_dir))
    print(f"Files: {[f['name'] for f in result.get('files', [])]}")
    print(f"Hidden files: {result.get('hidden_files', [])}")
    print(f"Total entries: {len(result.get('entries', []))}")
    print(f"Hidden entries count: {sum(1 for e in result.get('entries', []) if e.get('is_hidden', False))}")
    
    # Test with hiding hidden files
    print("\nTest 2: With hide_hidden=True")
    result = search_tools.ls(str(test_dir), hide_hidden=True)
    print(f"Files: {[f['name'] for f in result.get('files', [])]}")
    print(f"Hidden files: {result.get('hidden_files', [])}")
    print(f"Total entries: {len(result.get('entries', []))}")
    print(f"Hidden entries count: {sum(1 for e in result.get('entries', []) if e.get('is_hidden', False))}")
    
    # Cleanup
    for file in test_dir.glob("*"):
        file.unlink()
    test_dir.rmdir()
    
    print("\nTest completed")

if __name__ == "__main__":
    asyncio.run(test_ls_feature())
