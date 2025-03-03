#!/usr/bin/env python

"""
Unit tests for the DisplayManager class
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Output.display_manager import DisplayManager

def test_display_manager():
    """Test the display manager functionality"""
    print("\n=== Testing DisplayManager ===")
    display = DisplayManager()
    
    # Set verbosity level
    display._config.set("verbose_level", 2)
    display._config.set("verbose_output", True)
    
    # Test command result display
    print("\nTesting command result display:")
    test_result = {
        "stdout": "file1\nfile2\nfile3\nfile4\nfile5\nfile6\nfile7\nfile8\nfile9\nfile10",
        "stderr": "",
        "code": 0,
        "success": True
    }
    display.display_command_result("ls -la", test_result)
    
    # Test error display
    print("\nTesting error display:")
    error_result = {
        "stdout": "",
        "stderr": "No such file or directory",
        "code": 1,
        "success": False
    }
    display.display_command_result("cat nonexistent.txt", error_result)
    
    return True

if __name__ == "__main__":
    result = test_display_manager()
    print(f"Test result: {'PASSED' if result else 'FAILED'}")
    sys.exit(0 if result else 1)