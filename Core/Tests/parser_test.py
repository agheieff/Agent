"""
Tests for the ToolParser class.
"""

import pytest
from Tools.parser import ToolParser

class TestToolParser:
    """Test suite for the ToolParser class."""

    def test_simple_command(self):
        """Test parsing a simple command."""
        message = "/view /etc/hosts"
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "view"
        assert "value" in params
        assert params["value"] == "/etc/hosts"
        assert is_help is False

    def test_named_parameters(self):
        """Test parsing named parameters."""
        message = "/view file_path=/etc/hosts offset=10 limit=20"
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "view"
        assert params["file_path"] == "/etc/hosts"
        assert params["offset"] == "10"
        assert params["limit"] == "20"
        assert is_help is False

    def test_quoted_parameters(self):
        """Test parsing parameters with quoted values."""
        message = '/write file_path="/tmp/file with spaces.txt" content="Hello, world!"'
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "write"
        assert params["file_path"] == "/tmp/file with spaces.txt"
        assert params["content"] == "Hello, world!"
        assert is_help is False

    def test_help_parameter(self):
        """Test parsing help parameter."""
        message = "/view -h"
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "view"
        assert params == {}
        assert is_help is True

        # Test alternative help format
        message = "/view --help"
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "view"
        assert params == {}
        assert is_help is True

    def test_multiple_commands(self):
        """Test parsing multiple commands in a single message."""
        message = """
        Here's what I'll do:
        
        /view /etc/hosts
        
        Now let's create a file:
        
        /write file_path=/tmp/test.txt content="Hello, world!"
        """
        
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 2
        
        # First command
        tool_name, params, is_help = tool_calls[0]
        assert tool_name == "view"
        assert params["value"] == "/etc/hosts"
        
        # Second command
        tool_name, params, is_help = tool_calls[1]
        assert tool_name == "write"
        assert params["file_path"] == "/tmp/test.txt"
        assert params["content"] == "Hello, world!"

    def test_heredoc_parameters(self):
        """Test parsing parameters with heredoc-style multiline values."""
        message = """/write file_path=/tmp/test.py content="""
import os
import sys

def main():
    print("Hello, world!")
    print(f"Current directory: {os.getcwd()}")
    
if __name__ == "__main__":
    main()
"""
"""
        
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "write"
        assert params["file_path"] == "/tmp/test.py"
        assert "import os" in params["content"]
        assert "if __name__ == \"__main__\":" in params["content"]
        assert is_help is False

    def test_mixed_heredoc_and_regular_parameters(self):
        """Test parsing a mix of heredoc and regular parameters."""
        message = """/replace file_path=/tmp/config.yaml content="""
database:
  host: localhost
  port: 5432
  username: user
  password: pass
""" backup=true
"""
        
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "replace"
        assert params["file_path"] == "/tmp/config.yaml"
        assert "database:" in params["content"]
        assert "password: pass" in params["content"]
        assert params["backup"] == "true"
        assert is_help is False

    def test_single_quotes_heredoc(self):
        """Test parsing heredoc with single quotes."""
        message = """/write file_path=/tmp/test.txt content='''
This is a test
with multiple lines
using single quotes
for the heredoc
'''
"""
        
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "write"
        assert params["file_path"] == "/tmp/test.txt"
        assert "This is a test" in params["content"]
        assert "using single quotes" in params["content"]
        assert is_help is False

    def test_multiple_heredoc_parameters(self):
        """Test parsing multiple heredoc parameters in a single command."""
        message = """/edit file_path=/tmp/test.txt old_string="""
Original
multiline
content
""" new_string="""
New
updated
content
"""
"""
        
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        
        assert tool_name == "edit"
        assert params["file_path"] == "/tmp/test.txt"
        assert "Original" in params["old_string"]
        assert "New" in params["new_string"]
        assert is_help is False

    def test_complex_message_with_heredoc(self):
        """Test parsing a complex message with multiple commands and heredoc."""
        message = """
Let me create a simple Python program with two files.

First, let's create the main script:

/write file_path=main.py content="""
import helper

def main():
    print("Main program")
    helper.say_hello()

if __name__ == "__main__":
    main()
"""

Now, let's create the helper module:

/write file_path=helper.py content="""
def say_hello():
    print("Hello from helper module!")
"""

Let's check what we've created:

/view main.py
"""
        
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 3
        
        # First command
        tool_name, params, is_help = tool_calls[0]
        assert tool_name == "write"
        assert params["file_path"] == "main.py"
        assert "import helper" in params["content"]
        
        # Second command
        tool_name, params, is_help = tool_calls[1]
        assert tool_name == "write"
        assert params["file_path"] == "helper.py"
        assert "def say_hello()" in params["content"]
        
        # Third command
        tool_name, params, is_help = tool_calls[2]
        assert tool_name == "view"
        assert params["value"] == "main.py"

    def test_empty_message(self):
        """Test parsing an empty message."""
        message = ""
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 0

    def test_message_without_tools(self):
        """Test parsing a message with no tool calls."""
        message = "This is a message without any tool calls."
        tool_calls = ToolParser.extract_tool_calls(message)
        
        assert len(tool_calls) == 0


if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
