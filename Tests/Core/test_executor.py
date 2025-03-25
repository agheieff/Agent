import unittest
from unittest.mock import MagicMock, patch
from Core.executor import Executor, parse_tool_call, format_tool_result
from Tools.base import ToolResult

class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = Executor()
        self.mock_tool = MagicMock()
        self.mock_tool.name = "mock_tool"
        self.mock_tool.execute.return_value = ToolResult(ok=True, code=0, message="Success")
        self.executor.tools = {'mock_tool': self.mock_tool}

    def test_parse_tool_call_single_line(self):
        call_text = """@tool mock_tool
arg1: value1
arg2: value2
@end"""
        result = parse_tool_call(call_text)
        self.assertEqual(result['tool'], 'mock_tool')
        self.assertEqual(result['args'], {'arg1': 'value1', 'arg2': 'value2'})

    def test_parse_tool_call_multi_line(self):
        call_text = """@tool mock_tool
arg1: value1
multi: <<<
Line 1
  Line 2
    Line 3
>>>
arg2: value2
@end"""
        result = parse_tool_call(call_text)
        expected_content = "Line 1\n  Line 2\n    Line 3"
        self.assertEqual(result['args']['multi'], expected_content)
        self.assertEqual(result['args']['arg2'], 'value2')

    def test_format_tool_result_success(self):
        result = format_tool_result("test_tool", True, "Success message")
        expected = """@result test_tool
status: success
output: Success message
@end"""
        self.assertEqual(result.strip(), expected.strip())

    def test_format_tool_result_error(self):
        result = format_tool_result("test_tool", False, "Error message")
        expected = """@result test_tool
status: error
output: Error message
@end"""
        self.assertEqual(result.strip(), expected.strip())

    def test_execute_success(self):
        call_text = """@tool mock_tool
arg1: value1
arg2: value2
@end"""
        result = self.executor.execute(call_text)
        self.assertIn("status: success", result)
        self.assertIn("output: Success", result)
        self.mock_tool.execute.assert_called_once_with(arg1='value1', arg2='value2')

    def test_execute_tool_not_found(self):
        call_text = """@tool unknown_tool
arg1: value1
@end"""
        result = self.executor.execute(call_text)
        self.assertIn("status: error", result)
        self.assertIn("Tool 'unknown_tool' not found", result)

    def test_execute_tool_error(self):
        self.mock_tool.execute.side_effect = Exception("Test error")
        call_text = """@tool mock_tool
arg1: value1
@end"""
        result = self.executor.execute(call_text)
        self.assertIn("status: error", result)
        self.assertIn("Test error", result)

if __name__ == '__main__':
    unittest.main()
