#!/usr/bin/env python

"""
Unit tests for the CommandExtractor class
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Core.agent import CommandExtractor

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

if __name__ == "__main__":
    result = test_command_extractor()
    print(f"Test result: {'PASSED' if result else 'FAILED'}")
    sys.exit(0 if result else 1)