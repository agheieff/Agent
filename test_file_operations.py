"""Test script for file operations in the agent."""

import asyncio
import logging
from Core.agent import CommandExtractor, SystemControl

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_edit_operation():
    """Test the edit operation directly."""
    print("Testing edit operation...")
    system_control = SystemControl(test_mode=False)
    
    # Create a test file
    test_file = "/tmp/test_file.txt"
    original_content = "This is a test file for the agent to edit."
    
    # Write the original content
    await system_control.replace_file(test_file, original_content)
    
    # Display the original content
    print(f"Original content of {test_file}:")
    content = await system_control.view_file(test_file)
    print(content)
    
    # Test edit operation
    print("\nTesting edit...")
    edit_result = await system_control.edit_file(
        test_file,
        "test file",
        "MODIFIED test file"
    )
    print(f"Edit result: {edit_result}")
    
    # Display the modified content
    print(f"\nModified content of {test_file}:")
    content = await system_control.view_file(test_file)
    print(content)
    
    # Test edit through an agent-like XML command
    print("\nTesting edit through XML parsing...")
    
    # Create a CommandExtractor
    command_extractor = CommandExtractor()
    
    # Example XML command like what the LLM would generate
    xml_command = """<edit>
file_path: /tmp/test_file.txt
old_string: MODIFIED test file
new_string: TRIPLE MODIFIED test file with
  multi-line
  content
</edit>"""
    
    # Extract the command
    commands = command_extractor.extract_commands(xml_command)
    if commands:
        print(f"Extracted commands: {commands}")
        
        # Process the command manually
        for cmd_type, cmd in commands:
            print(f"Processing {cmd_type} command...")
            
            # Parse parameters using safer line-by-line parsing with better handling of indentation
            params = {}
            lines = cmd.split('\n')
            current_key = None
            current_value = []
            
            for i, line in enumerate(lines):
                line = line.rstrip()
                
                # Check if this is a new parameter line (contains a colon and isn't indented)
                if ":" in line and not line.startswith(" ") and not line.startswith("\t"):
                    # Save previous parameter if there was one
                    if current_key:
                        params[current_key] = '\n'.join(current_value).strip()
                        print(f"Extracted parameter: {current_key} = {params[current_key][:30]}{'...' if len(params[current_key]) > 30 else ''}")
                    
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
                print(f"Extracted parameter: {current_key} = {params[current_key][:30]}{'...' if len(params[current_key]) > 30 else ''}")
            
            print(f"Parsed parameters: {params}")
            
            # Execute command
            if cmd_type == "edit":
                file_path = params.get("file_path")
                old_string = params.get("old_string", "")
                new_string = params.get("new_string", "")
                
                if file_path:
                    print(f"Editing {file_path}...")
                    edit_result = await system_control.edit_file(file_path, old_string, new_string)
                    print(f"XML edit result: {edit_result}")
                    
                    # Display the final content
                    print(f"\nFinal content of {test_file}:")
                    content = await system_control.view_file(test_file)
                    print(content)
                else:
                    print("Error: Missing file_path parameter")
    else:
        print("No commands extracted from the XML")

async def main():
    await test_edit_operation()

if __name__ == "__main__":
    asyncio.run(main())