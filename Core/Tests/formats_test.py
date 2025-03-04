import pytest
import json
from Core.formats import AnthropicToolsParser, DeepseekToolsParser, XMLFormatParser

class TestAnthropicToolsParser:
    def setup_method(self):
        self.parser = AnthropicToolsParser()

    def test_can_parse_valid_format(self):

        message = """I'll help you with that.

tool_use: {
  "name": "search",
  "input": {
    "query": "weather in San Francisco"
  }
}
"""
        assert self.parser.can_parse(message) is True

    def test_can_parse_invalid_format(self):

        message = "I'll help you with that."
        assert self.parser.can_parse(message) is False


        assert self.parser.can_parse(123) is False

    def test_parse_valid_message(self):
        message = """I'll help you with that.

tool_use: {
  "name": "search",
  "input": {
    "query": "weather in San Francisco"
  }
}
"""
        result = self.parser.parse(message)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"
        assert result["tool_calls"][0]["params"]["query"] == "weather in San Francisco"

    def test_parse_multiple_tool_calls(self):
        message = """I'll use multiple tools.

tool_use: {
  "name": "search",
  "input": {
    "query": "weather in San Francisco"
  }
}

Now I'll check another source.

tool_use: {
  "name": "read_file",
  "input": {
    "path": "/tmp/data.txt"
  }
}
"""
        result = self.parser.parse(message)

        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["name"] == "search"
        assert result["tool_calls"][1]["name"] == "read_file"

    def test_parse_invalid_json(self):
        message = """tool_use: {
  "name": "search",
  input: "malformed json"
}
"""
        result = self.parser.parse(message)


        assert len(result["tool_calls"]) == 0

class TestDeepseekToolsParser:
    def setup_method(self):
        self.parser = DeepseekToolsParser()

    def test_can_parse_valid_format(self):

        message = json.dumps({
            "action": "search",
            "action_input": {
                "query": "weather in San Francisco"
            }
        })
        assert self.parser.can_parse(message) is True


        message = json.dumps({
            "action": "search",
            "parameters": {
                "query": "weather in San Francisco"
            }
        })
        assert self.parser.can_parse(message) is True

    def test_can_parse_invalid_format(self):

        message = json.dumps({
            "parameters": {
                "query": "weather in San Francisco"
            }
        })
        assert self.parser.can_parse(message) is False


        message = "This is not JSON"
        assert self.parser.can_parse(message) is False


        assert self.parser.can_parse(123) is False

    def test_parse_valid_message(self):
        message = json.dumps({
            "action": "search",
            "action_input": {
                "query": "weather in San Francisco"
            },
            "thinking": "I need to search for the weather",
            "reasoning": "The user asked about weather"
        })

        result = self.parser.parse(message)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"
        assert result["tool_calls"][0]["params"]["query"] == "weather in San Francisco"
        assert result["thinking"] == "I need to search for the weather"
        assert result["analysis"] == "The user asked about weather"

    def test_parse_with_string_params(self):
        message = json.dumps({
            "action": "search",
            "action_input": "weather in San Francisco"
        })

        result = self.parser.parse(message)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"
        assert result["tool_calls"][0]["params"]["value"] == "weather in San Francisco"

    def test_parse_with_parameters_field(self):
        message = json.dumps({
            "action": "search",
            "parameters": {
                "query": "weather in San Francisco"
            }
        })

        result = self.parser.parse(message)

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"
        assert result["tool_calls"][0]["params"]["query"] == "weather in San Francisco"

class TestXMLFormatParser:
    def setup_method(self):
        self.parser = XMLFormatParser()

    def test_can_parse_valid_format(self):

        message = "<agent_response><answer>Hello</answer></agent_response>"
        assert self.parser.can_parse(message) is True

    def test_can_parse_invalid_format(self):

        message = "This is not XML"
        assert self.parser.can_parse(message) is False

    def test_parse_valid_message(self):
        message = """
        <agent_response>
            <thinking>I need to analyze this</thinking>
            <analysis>The user wants information</analysis>
            <tool_calls>
                <tool name="search" help="false">
                    <params>
                        <param name="query">weather in San Francisco</param>
                    </params>
                </tool>
            </tool_calls>
            <answer>Here is the information</answer>
        </agent_response>
        """

        result = self.parser.parse(message)

        assert result["thinking"] == "I need to analyze this"
        assert result["analysis"] == "The user wants information"
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "search"
        assert result["tool_calls"][0]["params"]["query"] == "weather in San Francisco"
        assert result["answer"] == "Here is the information"

    def test_parse_invalid_xml(self):
        message = "<broken_xml>This is broken"

        result = self.parser.parse(message)


        assert result["tool_calls"] == []
        assert result["answer"] == message

if __name__ == "__main__":
    pytest.main(["-v"])
