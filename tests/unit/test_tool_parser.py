"""
Tests for the tool parser module.
"""

import unittest
from Core.tool_parser import ToolParser

class TestToolParser(unittest.TestCase):
    """Test cases for the ToolParser class."""

    def test_extract_tools_slash_command(self):
        """Test extracting slash command tool invocations."""
        message = "Here is some text.\n/bash ls -la\nMore text here."
        tools = ToolParser.extract_tools(message)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0], "/bash ls -la")

    def test_extract_tools_code_block(self):
        """Test extracting code block tool invocations."""
        message = """Here is some text.
```
bash
command: ls -la
timeout: 30
```
More text here."""
        tools = ToolParser.extract_tools(message)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0], "bash\ncommand: ls -la\ntimeout: 30")

    def test_extract_tools_mixed(self):
        """Test extracting mixed tool invocations."""
        message = """Let me help with that.
/search query: python examples

Also, you can run this command:
```tool
bash
command: find . -name "*.py" | grep test
```

And finally, /help to see available commands."""
        tools = ToolParser.extract_tools(message)
        self.assertEqual(len(tools), 3)
        self.assertEqual(tools[0], "/search query: python examples")
        self.assertEqual(tools[1], "bash\ncommand: find . -name \"*.py\" | grep test")
        self.assertEqual(tools[2], "/help")

    def test_parse_tool_slash_command(self):
        """Test parsing slash commands."""
        tool_text = "/bash ls -la"
        tool_name, params = ToolParser.parse_tool(tool_text)
        self.assertEqual(tool_name, "bash")
        self.assertEqual(params, {"value": "ls -la"})

    def test_parse_tool_multiline(self):
        """Test parsing multiline tool invocations."""
        tool_text = """bash
command: find . -name "*.py"
timeout: 30
verbose: true"""
        tool_name, params = ToolParser.parse_tool(tool_text)
        self.assertEqual(tool_name, "bash")
        self.assertEqual(params, {
            "command": 'find . -name "*.py"',
            "timeout": "30",
            "verbose": "true"
        })

    def test_parse_tool_with_equal_sign(self):
        """Test parsing tool with parameters using equal signs."""
        tool_text = """search
query=python examples
max_results=5"""
        tool_name, params = ToolParser.parse_tool(tool_text)
        self.assertEqual(tool_name, "search")
        self.assertEqual(params, {
            "query": "python examples",
            "max_results": "5"
        })

    def test_parse_tool_with_positional_args(self):
        """Test parsing tool with positional arguments."""
        tool_text = """compile
main.c
-o
app
-Wall"""
        tool_name, params = ToolParser.parse_tool(tool_text)
        self.assertEqual(tool_name, "compile")
        self.assertEqual(params, {
            "args": ["main.c", "-o", "app", "-Wall"]
        })

    def test_process_message(self):
        """Test processing a complete message."""
        message = """Let me help with that.
/bash ls -la

Also try:
```
search
query: python examples
max_results: 5
```"""
        tools = list(ToolParser.process_message(message))
        self.assertEqual(len(tools), 2)
        
        self.assertEqual(tools[0][0], "bash")
        self.assertEqual(tools[0][1], {"value": "ls -la"})
        
        self.assertEqual(tools[1][0], "search")
        self.assertEqual(tools[1][1], {
            "query": "python examples",
            "max_results": "5"
        })

    def test_empty_message(self):
        """Test processing an empty message."""
        message = ""
        tools = list(ToolParser.process_message(message))
        self.assertEqual(len(tools), 0)

    def test_message_with_no_tools(self):
        """Test processing a message with no tool invocations."""
        message = "This is a regular message with no tools or commands."
        tools = list(ToolParser.process_message(message))
        self.assertEqual(len(tools), 0)

    def test_format_result(self):
        """Test formatting tool execution results."""
        result = ToolParser.format_result("bash", True, "Command output")
        self.assertEqual(result, {
            "tool": "bash",
            "success": True,
            "output": "Command output"
        })
        
        result = ToolParser.format_result("search", False, error="Search failed")
        self.assertEqual(result, {
            "tool": "search",
            "success": False,
            "error": "Search failed"
        })

if __name__ == "__main__":
    unittest.main()