#!/usr/bin/env python

"""
Integration test for file operations
"""

import sys
import os
import asyncio
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from Core.agent import CommandExtractor, SystemControl

async def test_edit_operation():
    """Test the edit operation directly."""
    print("\n=== Testing Edit File Operation ===")
    system_control = SystemControl(test_mode=False)
    
    # Create a test file
    test_file = Path(__file__).parent.parent / "temp" / "test_file.txt"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    
    original_content = "This is a test file for the agent to edit."
    
    try:
        # Write the original content
        await system_control.replace_file(str(test_file), original_content)
        
        # Display the original content
        print(f"Original content of {test_file}:")
        content = await system_control.view_file(str(test_file))
        print(content)
        
        # Test edit operation
        print("\nTesting edit...")
        edit_result = await system_control.edit_file(
            str(test_file),
            "test file",
            "MODIFIED test file"
        )
        print(f"Edit result: {edit_result}")
        
        # Display the modified content
        print(f"\nModified content of {test_file}:")
        content = await system_control.view_file(str(test_file))
        print(content)
        
        # Verify content changed
        assert "MODIFIED" in content, "Content should contain 'MODIFIED'"
        assert "test file" not in content, "Original content should be replaced"
        
        # Test edit through an agent-like XML command
        print("\nTesting edit through XML parsing...")
        
        # Create a CommandExtractor
        command_extractor = CommandExtractor()
        
        # Example XML command like what the LLM would generate
        xml_command = f"""<edit>
file_path: {test_file}
old_string: MODIFIED test file
new_string: TRIPLE MODIFIED test file with
  multi-line
  content
</edit>"""
        
        # Extract the command
        commands = command_extractor.extract_commands(xml_command)
        assert commands, "Should extract commands from XML"
        
        # Process the extracted command
        cmd_type, cmd = commands[0]
        assert cmd_type == "edit", f"Command type should be 'edit', got '{cmd_type}'"
        
        # Parse parameters using simpler line-by-line parsing
        params = {}
        lines = cmd.split('\n')
        current_key = None
        current_value = []
        
        for line in lines:
            if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                # Save previous parameter if there was one
                if current_key:
                    params[current_key] = '\n'.join(current_value).strip()
                
                # Start new parameter
                parts = line.split(":", 1)
                current_key = parts[0].strip()
                current_value = [parts[1].strip()]
            elif current_key:
                # This is a continuation line (part of the current parameter value)
                current_value.append(line)
        
        # Save the last parameter
        if current_key and current_value:
            params[current_key] = '\n'.join(current_value).strip()
        
        # Execute command
        file_path = params.get("file_path")
        old_string = params.get("old_string", "")
        new_string = params.get("new_string", "")
        
        assert file_path, "File path should be extracted from XML"
        assert old_string, "Old string should be extracted from XML"
        assert new_string, "New string should be extracted from XML"
        
        edit_result = await system_control.edit_file(file_path, old_string, new_string)
        print(f"XML edit result: {edit_result}")
        
        # Display the final content
        print(f"\nFinal content of {test_file}:")
        content = await system_control.view_file(str(test_file))
        print(content)
        
        # Verify final content
        assert "TRIPLE MODIFIED" in content, "Content should contain 'TRIPLE MODIFIED'"
        assert "multi-line" in content, "Content should contain multi-line text"
        
        print("\n✅ File operation tests passed")
        return True
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    finally:
        # Clean up
        if test_file.exists():
            test_file.unlink()

if __name__ == "__main__":
    result = asyncio.run(test_edit_operation())
    sys.exit(0 if result else 1)