import pytest
from Core.parser import ToolParser

class TestToolParser:
    def test_simple_command(self):
        message = "/read /etc/hosts"
        tool_calls = ToolParser.extract_tool_calls(message)
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        assert tool_name == "read"
        assert params.get("value") == "/etc/hosts"
        assert is_help is False

    def test_help_flag(self):
        message = "/read -h"
        tool_calls = ToolParser.extract_tool_calls(message)
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        assert tool_name == "read"
        assert params == {}
        assert is_help is True

    def test_named_parameters(self):
        message = '/read file_path=/etc/hosts offset=10 limit=20'
        tool_calls = ToolParser.extract_tool_calls(message)
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        assert tool_name == "read"
        assert params.get("file_path") == "/etc/hosts"
        assert params.get("offset") == "10"
        assert params.get("limit") == "20"
        assert is_help is False

if __name__ == "__main__":
    pytest.main(["-v"])
