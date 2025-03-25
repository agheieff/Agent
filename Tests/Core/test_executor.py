import unittest
from unittest.mock import MagicMock, patch
from Core.executor import Executor, parse_tool_call, format_result
from Tools.base import ToolResult

class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = Executor()
        self.mock_tool = MagicMock()
        self.mock_tool.name = "mock_tool"
        self.mock_tool.execute.return_value = (0, "Success")
        self.executor.tools = {'mock_tool': self.mock_tool}

    def test_format_result_success(self):
        result = format_result("test_tool", 0, "Success message")
        expected = """@result test_tool
exit_code: 0
output: Success message
@end"""
        self.assertEqual(result.strip(), expected.strip())

    def test_format_result_error(self):
        result = format_result("test_tool", 1, "Error message")
        expected = """@result test_tool
exit_code: 1
output: Error message
@end"""
        self.assertEqual(result.strip(), expected.strip())

    def test_execute_success(self):
        call_text = """@tool mock_tool
arg1: value1
arg2: value2
@end"""
        result = self.executor.execute(call_text)
        self.assertIn("exit_code: 0", result)
        self.assertIn("output: Success", result)
        self.mock_tool.execute.assert_called_once_with(arg1='value1', arg2='value2')

    def test_execute_tool_not_found(self):
        call_text = """@tool unknown_tool
arg1: value1
@end"""
        result = self.executor.execute(call_text)
        self.assertIn("exit_code: 1", result)
        self.assertIn("Tool not found", result)

    def test_execute_tool_error(self):
        self.mock_tool.execute.return_value = (1, "Test error")
        call_text = """@tool mock_tool
arg1: value1
@end"""
        result = self.executor.execute(call_text)
        self.assertIn("exit_code: 1", result)
        self.assertIn("Test error", result)

if __name__ == '__main__':
    unittest.main()
