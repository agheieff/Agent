import unittest
from Prompts.main import generate_system_prompt

class TestPromptConstruction(unittest.TestCase):
    def test_prompt_contains_sections(self):
        # Generate the prompt for a sample provider (e.g., "anthropic")
        prompt = generate_system_prompt("anthropic")
        
        # Check that the major sections are present in the prompt
        self.assertIn("# ROLE", prompt, "Missing ROLE section")
        self.assertIn("# TOOL USAGE", prompt, "Missing TOOL USAGE section")
        self.assertIn("# FILE PATHS", prompt, "Missing FILE PATHS section")
        self.assertIn("# TOOLS", prompt, "Missing TOOLS section")
        self.assertIn("# TOOL OVERVIEW", prompt, "Missing TOOL OVERVIEW section")
        
        # Verify that the overview includes a file structure section
        self.assertIn("File Structure of Tools Directory:", prompt, "Missing file structure information")
        
        # Verify that a list of available tools is included (check for at least one known tool name)
        known_tools = ["read_file", "edit_file", "delete_file", "ls", "write_file", "end", "message", "pause"]
        found_tool = any(tool in prompt for tool in known_tools)
        self.assertTrue(found_tool, "None of the expected tool names were found in the prompt")

if __name__ == "__main__":
    unittest.main()
