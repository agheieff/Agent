#!/usr/bin/env python

"""
Test integration between the message parser and tool executor.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Core.parser import process_message

async def main():
    """Run integration test between parser and executor."""
    # Test message with multiple tool invocations
    message = """
Let me help you with that task.

First, let's check the current directory:
/bash pwd

Now let's look at Python files:
```
bash
command: find . -name "*.py" | grep -v "__pycache__" | head -n 5
```

Let's also get some basic help:
/help
"""

    print("Processing message with tools...")
    results = await process_message(message)
    
    print("\nExecution Results:")
    for i, result in enumerate(results):
        print(f"\n--- Tool {i+1} ---")
        print(f"Tool: {result['tool']}")
        print(f"Parameters: {result['params']}")
        print(f"Success: {result['success']}")
        print(f"Exit Code: {result['exit_code']}")
        
        if result['output']:
            print(f"Output:\n{result['output']}")
        
        if result['error']:
            print(f"Error:\n{result['error']}")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(1)