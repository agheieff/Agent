import pytest
import json
from Core.parser import ToolParser, CLIFormatParser, JSONFormatParser
from Core.formats import XMLFormatParser

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

    def test_help_flag_long_form(self):
        message = "/read --help"
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

    def test_multiple_commands(self):
        message = "/read /etc/hosts\n/write file_path=/tmp/test.txt content=hello"
        tool_calls = ToolParser.extract_tool_calls(message)
        assert len(tool_calls) == 2

        tool_name1, params1, is_help1 = tool_calls[0]
        assert tool_name1 == "read"
        assert params1.get("value") == "/etc/hosts"
        assert is_help1 is False

        tool_name2, params2, is_help2 = tool_calls[1]
        assert tool_name2 == "write"
        assert params2.get("file_path") == "/tmp/test.txt"
        assert params2.get("content") == "hello"
        assert is_help2 is False

    def test_no_commands(self):
        message = "This is a regular message without any commands"
        tool_calls = ToolParser.extract_tool_calls(message)
        assert len(tool_calls) == 0

    def test_command_with_no_parameters(self):
        message = "/help"
        tool_calls = ToolParser.extract_tool_calls(message)
        assert len(tool_calls) == 1
        tool_name, params, is_help = tool_calls[0]
        assert tool_name == "help"
        assert params == {}
        assert is_help is False

    def test_parse_message_valid_json(self, tool_parser):
        json_str = json.dumps({
            "thinking": "I need to read a file",
            "analysis": "Looking at file structure",
            "tool_calls": [{"name": "read", "params": {"file_path": "/etc/hosts"}}],
            "answer": "Here's the file content"
        })

        result = tool_parser.parse_message(json_str)
        assert result["thinking"] == "I need to read a file"
        assert result["analysis"] == "Looking at file structure"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"
        assert result["answer"] == "Here's the file content"

    def test_parse_message_invalid_json(self, tool_parser):
        message = "This is not a valid JSON"
        result = tool_parser.parse_message(message)
        assert result["thinking"] == ""
        assert result["analysis"] == ""
        assert result["tool_calls"] == []
        assert result["answer"] == message

    def test_parse_message_non_dict_json(self, tool_parser):
        json_str = json.dumps(["item1", "item2"])
        result = tool_parser.parse_message(json_str)
        assert result["thinking"] == ""
        assert result["analysis"] == ""
        assert result["tool_calls"] == []
        assert result["answer"] == json_str

    def test_parse_message_invalid_tool_calls(self, tool_parser):
        json_str = json.dumps({
            "thinking": "Test thinking",
            "tool_calls": "Not a list",
            "answer": "Test answer"
        })

        result = tool_parser.parse_message(json_str)
        assert result["thinking"] == "Test thinking"
        assert result["tool_calls"] == []
        assert result["answer"] == "Test answer"

    def test_cli_format_parser(self):
        parser = CLIFormatParser()
        assert parser.can_parse("/read file_path=/etc/hosts") == True
        assert parser.can_parse("Normal text") == False

        result = parser.parse("/read file_path=/etc/hosts")
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"
        assert result["tool_calls"][0]["params"]["file_path"] == "/etc/hosts"

    def test_json_format_parser(self):
        parser = JSONFormatParser()
        json_str = json.dumps({
            "thinking": "Test thinking",
            "tool_calls": [{"name": "read", "params": {"file_path": "/etc/hosts"}}],
            "answer": "Test answer"
        })

        assert parser.can_parse(json_str) == True
        assert parser.can_parse("Normal text") == False

        result = parser.parse(json_str)
        assert result["thinking"] == "Test thinking"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"
        assert result["answer"] == "Test answer"

    def test_xml_format_parser(self):
        parser = XMLFormatParser()
        xml_str = """
        <agent_response>
            <thinking>Test thinking</thinking>
            <tool_calls>
                <tool name="read">
                    <params>
                        <param name="file_path">/etc/hosts</param>
                    </params>
                </tool>
            </tool_calls>
            <answer>Test answer</answer>
        </agent_response>
        """

        assert parser.can_parse(xml_str) == True
        assert parser.can_parse("Normal text") == False

        result = parser.parse(xml_str)
        assert result["thinking"] == "Test thinking"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"
        assert result["tool_calls"][0]["params"]["file_path"] == "/etc/hosts"
        assert result["answer"] == "Test answer"

    def test_format_detection(self, tool_parser):

        cli_message = "/read file_path=/etc/hosts"
        result = tool_parser.parse_message(cli_message)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"


        json_message = json.dumps({
            "tool_calls": [{"name": "read", "params": {"file_path": "/etc/hosts"}}]
        })
        result = tool_parser.parse_message(json_message)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"


        xml_message = """
        <agent_response>
            <tool_calls>
                <tool name="read">
                    <params>
                        <param name="file_path">/etc/hosts</param>
                    </params>
                </tool>
            </tool_calls>
        </agent_response>
        """
        result = tool_parser.parse_message(xml_message)
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read"


        text_message = "This is plain text"
        result = tool_parser.parse_message(text_message)
        assert result["tool_calls"] == []
        assert result["answer"] == text_message

if __name__ == "__main__":
    pytest.main(["-v"])
