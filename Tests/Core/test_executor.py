import unittest
import os
from unittest.mock import patch, MagicMock
from Core.executor import Executor
from Tools.base import Tool, Argument, ArgumentType
from Tools.error_codes import ErrorCodes

# Mock tool for testing
class MockTool(Tool):
    def __init__(self):
        super().__init__(
            name="mock_tool",
            description="Test tool",
            args=[
                Argument("arg1", ArgumentType.STRING),
                Argument("multi", ArgumentType.STRING)
            ]
        )
    
    def _run(self, args):
        return {'success': True, 'output': f"Received: {args['arg1']}"}

class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = Executor()
        self.executor.tools = {'mock_tool': MockTool()}

    def test_single_line_arguments(self):
        call_text = """@tool mock_tool
arg1: value1
multi: single line
@end"""
        
        result = self.executor.execute(call_text)
        self.assertIn("@result mock_tool", result)
        self.assertIn("status: success", result)
        self.assertIn("Received: value1", result)

    def test_multi_line_block(self):
        call_text = """@tool mock_tool
arg1: test
multi: <<<
Line 1
  Line 2
    Line 3
>>>
@end"""
        
        result = self.executor.parse_tool_call(call_text)
        expected_content = "Line 1\n  Line 2\n    Line 3"
        self.assertEqual(result['args']['multi'], expected_content)

    def test_python_code_preservation(self):
        call_text = """@tool mock_tool
arg1: code_test
multi: <<<
def hello():
    if True:
        print("Hello")
    return 42
>>>
@end"""
        
        result = self.executor.parse_tool_call(call_text)
        expected_code = 'def hello():\n    if True:\n        print("Hello")\n    return 42'
        self.assertEqual(result['args']['multi'], expected_code)

    def test_mixed_arguments(self):
        call_text = """@tool mock_tool
arg1: first_value
multi: <<<
Multi-line
  content
>>>
arg2: last_value
@end"""
        
        with self.assertRaises(ValueError):
            self.executor.parse_tool_call(call_text)

    def test_unclosed_multi_line(self):
        call_text = """@tool mock_tool
arg1: value
multi: <<<
Unclosed
block
@end"""
        
        with self.assertRaises(ValueError):
            self.executor.parse_tool_call(call_text)

    def test_empty_multi_line(self):
        call_text = """@tool mock_tool
arg1: value
multi: <<<
>>>
@end"""
        
        result = self.executor.parse_tool_call(call_text)
        self.assertEqual(result['args']['multi'], "")

    def test_tool_not_found(self):
        call_text = """@tool unknown_tool
arg1: value
@end"""
        
        result = self.executor.execute(call_text)
        self.assertIn("status: error", result)
        self.assertIn("Tool not found", result)

    def test_missing_required_argument(self):
        call_text = """@tool mock_tool
multi: <<<
content
>>>
@end"""
        
        result = self.executor.execute(call_text)
        self.assertIn("status: error", result)
        self.assertIn("Missing required argument", result)

    def test_special_characters(self):
        call_text = """@tool mock_tool
arg1: normal_value
multi: <<<
Special chars: !@#$%^&*()
>>>
@end"""
        
        result = self.executor.parse_tool_call(call_text)
        self.assertEqual(result['args']['multi'], "Special chars: !@#$%^&*()")

    def test_multiple_multi_line_args(self):
        call_text = """@tool mock_tool
arg1: <<<
First
multi-line
>>>
multi: <<<
Second
multi-line
>>>
@end"""
        
        with self.assertRaises(ValueError):
            self.executor.parse_tool_call(call_text)

    def test_edge_cases(self):
        # Empty tool call
        with self.assertRaises(ValueError):
            self.executor.parse_tool_call("@tool @end")
        
        # Missing @end
        with self.assertRaises(ValueError):
            self.executor.parse_tool_call("@tool mock_tool\narg1: value")

    def test_execute_success(self):
        call_text = """@tool mock_tool
arg1: success_test
multi: <<<
content
>>>
@end"""
        
        result = self.executor.execute(call_text)
        self.assertIn("status: success", result)
        self.assertIn("Received: success_test", result)

    def test_execute_error(self):
        # Patch the tool to raise an error
        with patch.object(MockTool, '_run', side_effect=Exception("Test error")):
            call_text = """@tool mock_tool
arg1: error_test
multi: value
@end"""
            
            result = self.executor.execute(call_text)
            self.assertIn("status: error", result)
            self.assertIn("Test error", result)

if __name__ == '__main__':
    unittest.main()
