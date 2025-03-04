import json
import pytest
from Core.composer import ToolResponseComposer

class TestToolResponseComposer:
    def test_format_tool_result(self):
        tool_name = "read"
        params = {"file_path": "/etc/hosts"}
        result = {
            "success": True,
            "output": "Host file content",
            "error": ""
        }
        formatted = ToolResponseComposer.format_tool_result(tool_name, params, result)
        assert "Tool: read" in formatted
        assert "Parameters: file_path=/etc/hosts" in formatted
        assert "Success" in formatted
        assert "Output:" in formatted

    def test_compose_json_response(self):
        tool_results = [
            ("read", {"file_path": "/etc/hosts"}, {"success": True, "output": "Content", "error": ""})
        ]
        json_response = ToolResponseComposer.compose_json_response(tool_results)
        parsed = json.loads(json_response)
        assert "results" in parsed
        assert parsed["results"][0]["tool"] == "read"
        assert parsed["results"][0]["output"] == "Content"
