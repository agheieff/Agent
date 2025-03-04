import json
import pytest
from Core.composer import ToolResponseComposer, TextFormatComposer, JSONFormatComposer
from Core.formats import XMLFormatComposer

class TestToolResponseComposer:
    def test_format_tool_result(self):
        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Host file content",
            "error": ""
        }
        composer = ToolResponseComposer()
        formatted = composer.format_tool_result(tool_name, params, result)
        assert "Tool: read" in formatted
        assert "Parameters: file_path=/etc/hosts" in formatted
        assert "Status: Success" in formatted
        assert "Output:" in formatted
        assert "Host file content" in formatted

    def test_format_tool_result_with_error(self):
        tool_name = "read"
        params = {"file_path": "/nonexistent"}
        result = {
            "success": False,
            "output": "",
            "error": "File not found"
        }
        composer = ToolResponseComposer()
        formatted = composer.format_tool_result(tool_name, params, result)
        assert "Tool: read" in formatted
        assert "Parameters: file_path=/nonexistent" in formatted
        assert "Status: Failed" in formatted
        assert "Error: File not found" in formatted

    def test_format_tool_result_with_multiline_param(self):
        tool_name = "write"
        params = {"file_path": "/tmp/test.txt", "content": "line1\nline2\nline3"}
        result = {
            "success": True,
            "output": "File written",
            "error": ""
        }
        composer = ToolResponseComposer()
        formatted = composer.format_tool_result(tool_name, params, result)
        assert "Tool: write" in formatted
        assert "Parameters: file_path=/tmp/test.txt, content=<multiline content>" in formatted
        assert "Status: Success" in formatted

    def test_format_tool_result_with_complex_param(self):
        tool_name = "process"
        params = {"file_path": "/tmp/test.txt", "options": {"recursive": True, "follow_symlinks": False}}
        result = {
            "success": True,
            "output": "Processing complete",
            "error": ""
        }
        composer = ToolResponseComposer()
        formatted = composer.format_tool_result(tool_name, params, result)
        assert "Tool: process" in formatted
        assert "Parameters: file_path=/tmp/test.txt, options=<complex value>" in formatted
        assert "Status: Success" in formatted

    def test_format_tool_result_as_json(self):
        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Host file content",
            "error": ""
        }
        composer = ToolResponseComposer()
        json_result = composer.format_tool_result(tool_name, params, result, format_name="json")
        assert json_result["tool"] == "read"
        assert json_result["params"] == params
        assert json_result["success"] is True
        assert json_result["output"] == "Host file content"
        assert json_result["error"] == ""
        assert json_result["exit_code"] == 0

    def test_format_tool_result_as_json_with_error(self):
        tool_name = "read"
        params = {"file_path": "/nonexistent"}
        result = {
            "success": False,
            "output": "",
            "error": "File not found"
        }
        composer = ToolResponseComposer()
        json_result = composer.format_tool_result(tool_name, params, result, format_name="json")
        assert json_result["tool"] == "read"
        assert json_result["params"] == params
        assert json_result["success"] is False
        assert json_result["output"] == ""
        assert json_result["error"] == "File not found"
        assert json_result["exit_code"] == 1

    def test_compose_response_with_multiple_tools(self):
        tool_results = [
            ("read", {"file_path": "/etc/hosts"}, {"success": True, "output": "Content1", "error": ""}),
            ("write", {"file_path": "/tmp/test.txt"}, {"success": False, "output": "", "error": "Permission denied"})
        ]
        composer = ToolResponseComposer()
        response = composer.compose_response(tool_results)
        assert "I've executed the following tools:" in response
        assert "Tool: read" in response
        assert "Tool: write" in response
        assert "Content1" in response
        assert "Permission denied" in response
        assert "Please continue based on these results." in response

    def test_compose_response_with_no_tools(self):
        tool_results = []
        composer = ToolResponseComposer()
        response = composer.compose_response(tool_results)
        assert response == "No tools were executed."

    def test_compose_json_response(self):
        tool_results = [
            ("read", {"file_path": "/etc/hosts"}, {"success": True, "output": "Content", "error": ""})
        ]
        composer = ToolResponseComposer()
        json_response = composer.compose_response(tool_results, format_name="json")
        parsed = json.loads(json_response)
        assert "results" in parsed
        assert parsed["results"][0]["tool"] == "read"
        assert parsed["results"][0]["output"] == "Content"
        assert parsed["message"] == "Tool execution complete."

    def test_compose_json_response_with_no_tools(self):
        tool_results = []
        composer = ToolResponseComposer()
        json_response = composer.compose_response(tool_results, format_name="json")
        parsed = json.loads(json_response)
        assert "message" in parsed
        assert parsed["message"] == "No tools were executed."

    def test_compose_json_response_with_multiple_tools(self):
        tool_results = [
            ("read", {"file_path": "/etc/hosts"}, {"success": True, "output": "Content1", "error": ""}),
            ("write", {"file_path": "/tmp/test.txt"}, {"success": False, "output": "", "error": "Permission denied"})
        ]
        composer = ToolResponseComposer()
        json_response = composer.compose_response(tool_results, format_name="json")
        parsed = json.loads(json_response)
        assert "results" in parsed
        assert len(parsed["results"]) == 2
        assert parsed["results"][0]["tool"] == "read"
        assert parsed["results"][0]["output"] == "Content1"
        assert parsed["results"][1]["tool"] == "write"
        assert parsed["results"][1]["error"] == "Permission denied"

    def test_text_format_composer(self):
        composer = TextFormatComposer()
        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Host file content",
            "error": ""
        }

        formatted = composer.format_tool_result(tool_name, params, result)
        assert "Tool: read" in formatted
        assert "Parameters: file_path=/etc/hosts" in formatted
        assert "Status: Success" in formatted

        tool_results = [
            (tool_name, params, result)
        ]
        response = composer.compose_response(tool_results)
        assert "I've executed the following tools:" in response
        assert "Tool: read" in response

    def test_json_format_composer(self):
        composer = JSONFormatComposer()
        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Host file content",
            "error": ""
        }

        formatted = composer.format_tool_result(tool_name, params, result)
        assert formatted["tool"] == "read"
        assert formatted["params"] == params
        assert formatted["success"] is True

        tool_results = [
            (tool_name, params, result)
        ]
        response = composer.compose_response(tool_results)
        parsed = json.loads(response)
        assert "results" in parsed
        assert parsed["results"][0]["tool"] == "read"

    def test_xml_format_composer(self):
        composer = XMLFormatComposer()
        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Host file content",
            "error": ""
        }

        formatted = composer.format_tool_result(tool_name, params, result)
        assert "<name>read</name>" in formatted
        assert "<status>success</status>" in formatted
        assert "<output>Host file content</output>" in formatted

        tool_results = [
            (tool_name, params, result)
        ]
        response = composer.compose_response(tool_results)
        assert "<tool_results>" in response
        assert "<name>read</name>" in response
        assert "<output>Host file content</output>" in response

    def test_format_registration_and_selection(self, tool_composer):

        assert "text" in tool_composer.composers
        assert "json" in tool_composer.composers
        assert "xml" in tool_composer.composers


        assert tool_composer.default_format == "text"


        tool_composer.set_default_format("json")
        assert tool_composer.default_format == "json"


        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Content",
            "error": ""
        }


        formatted = tool_composer.format_tool_result(tool_name, params, result)
        assert isinstance(formatted, dict)
        assert formatted["tool"] == "read"


        formatted = tool_composer.format_tool_result(tool_name, params, result, format_name="xml")
        assert isinstance(formatted, str)
        assert "<name>read</name>" in formatted
