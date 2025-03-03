#\!/usr/bin/env python

"""
A focused test runner that tests specific agent functionality
"""

import asyncio
import sys
import os
import signal
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent))

from Core.agent import CommandExtractor
from Output.display_manager import DisplayManager

def test_command_extractor():
    """Test the command extractor functionality"""
    print("\n=== Testing CommandExtractor ===")
    extractor = CommandExtractor()
    
    # Test sample responses
    test_response = """
    I'll help you list the files. Let me run the ls command.
    
    <bash>
    ls -la
    </bash>
    
    <grep>
    pattern: import
    include: *.py
    </grep>
    
    <thinking>
    I need to check what's in the config file.
    </thinking>
    
    <user_input>
    Do you want to see hidden files too?
    </user_input>
    """
    
    # Extract commands
    commands = extractor.extract_commands(test_response)
    print(f"Extracted {len(commands)} commands:")
    for cmd_type, cmd in commands:
        print(f"- Type: {cmd_type}")
        print(f"  Content: {cmd[:40]}...")
    
    # Extract thinking
    thinking = extractor.extract_thinking(test_response)
    print(f"\nExtracted thinking: {thinking}")
    
    # Extract user input requests
    input_requests = extractor.extract_user_input_requests(test_response)
    print(f"Extracted input requests: {input_requests}")
    
    return len(commands) == 2 and len(thinking) == 1 and len(input_requests) == 1

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

def main():
    """Run all tests"""
    all_tests = [
        test_command_extractor,
        test_display_manager
    ]
    
    results = []
    for test in all_tests:
        try:
            result = test()
            results.append(result)
            print(f"{test.__name__}: {'PASS' if result else 'FAIL'}")
        except Exception as e:
            print(f"{test.__name__}: ERROR - {e}")
            results.append(False)
    
    print(f"\nTests: {sum(results)}/{len(results)} passed")
    return all(results)

if __name__ == "__main__":
    main()
