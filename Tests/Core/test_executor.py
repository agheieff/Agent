import unittest
import os
from datetime import datetime
from unittest.mock import patch, MagicMock
from Core.executor import Executor
from Tools.base import Tool, Argument, ErrorCodes, ArgumentType
from Tools.type_system import (
    validate_string, 
    validate_boolean, 
    validate_int, 
    validate_float, 
    validate_filepath, 
    validate_datetime
)

# Mock tool for testing
class MockTool(Tool):
    def __init__(self):
        super().__init__(
            name="mock_tool",
            description="A mock tool for testing",
            arguments=[
                Argument("arg1", ArgumentType.STRING)
            ]
        )
    
    def _execute(self, arg1="value1"):
        return 0, "Success"

class TypedTool(Tool):
    def __init__(self):
        super().__init__(
            name="typed_tool",
            description="A tool with typed arguments for testing",
            arguments=[
                Argument("string_arg", arg_type=ArgumentType.STRING, is_optional=False),
                Argument("int_arg", arg_type=ArgumentType.INT, is_optional=False),
                Argument("float_arg", arg_type=ArgumentType.FLOAT, is_optional=False),
                Argument("bool_arg", arg_type=ArgumentType.BOOLEAN, is_optional=False),
                Argument("filepath_arg", arg_type=ArgumentType.FILEPATH, is_optional=False),
                Argument("datetime_arg", arg_type=ArgumentType.DATETIME, is_optional=False),
                Argument("optional_arg", arg_type=ArgumentType.STRING, is_optional=True),
                Argument("default_arg", arg_type=ArgumentType.INT, is_optional=True, default_value=42)
            ]
        )
    
    def _execute(self, string_arg, int_arg, float_arg, bool_arg, filepath_arg, datetime_arg, 
                optional_arg=None, default_arg=42):
        # Simply return the received arguments as a formatted string
        args_dict = {
            "string_arg": string_arg,
            "int_arg": int_arg,
            "float_arg": float_arg,
            "bool_arg": bool_arg,
            "filepath_arg": filepath_arg,
            "datetime_arg": datetime_arg,
            "optional_arg": optional_arg,
            "default_arg": default_arg
        }
        return ErrorCodes.SUCCESS, str(args_dict)

class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.executor = Executor()
        
    def test_parse_tool_call_valid(self):
        call_text = """@tool mock_tool
arg1: value1
arg2: value2
@end"""
        tool_name, args = self.executor._parse_tool_call(call_text)
        
        self.assertEqual(tool_name, "mock_tool")
        self.assertEqual(args, {
            "arg1": "value1",
            "arg2": "value2"
        })
        
    def test_parse_tool_call_invalid_format(self):
        call_text = """not a valid tool call"""
        with self.assertRaises(ValueError):
            self.executor._parse_tool_call(call_text)
            
    def test_parse_tool_call_invalid_args(self):
        call_text = """@tool mock_tool
invalid_arg_line
@end"""
        with self.assertRaises(ValueError):
            self.executor._parse_tool_call(call_text)
            
    def test_parse_tool_call_empty_args(self):
        call_text = """@tool mock_tool
@end"""
        tool_name, args = self.executor._parse_tool_call(call_text)
        
        self.assertEqual(tool_name, "mock_tool")
        self.assertEqual(args, {})
        
    def test_parse_tool_call_with_spaces(self):
        call_text = """@tool   mock_tool  
  arg1:   value1  
  arg2:   value2  
@end"""
        tool_name, args = self.executor._parse_tool_call(call_text)
        
        self.assertEqual(tool_name, "mock_tool")
        self.assertEqual(args, {
            "arg1": "value1",
            "arg2": "value2"
        })
    
    @patch('importlib.util.spec_from_file_location')
    @patch('os.walk')
    def test_import_tool_success(self, mock_walk, mock_spec_from_file_location):
        # Mock the file system walk
        mock_walk.return_value = [
            ('/Tools', [], ['mock_tool.py'])
        ]
        
        # Mock the module loading
        mock_module = MagicMock()
        mock_module.MockTool = MockTool
        mock_spec = MagicMock()
        mock_spec.loader.exec_module = lambda m: setattr(m, 'MockTool', MockTool)
        mock_spec_from_file_location.return_value = mock_spec
        
        tool_class = self.executor._import_tool('mock_tool')
        self.assertEqual(tool_class().name, 'mock_tool')
    
    def test_import_tool_not_found(self):
        with self.assertRaises(ImportError):
            self.executor._import_tool('nonexistent_tool')
    
    @patch.object(Executor, '_import_tool')
    def test_execute_success(self, mock_import_tool):
        mock_import_tool.return_value = MockTool
        
        call_text = """@tool mock_tool
arg1: value1
@end"""
        exit_code, message = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, 0)
        self.assertEqual(message, "Success")
    
    def test_execute_invalid_format(self):
        call_text = "invalid format"
        exit_code, message = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, -1)
        self.assertTrue("Invalid tool call" in message)
    
    @patch.object(Executor, '_import_tool')
    def test_execute_tool_error(self, mock_import_tool):
        # Mock a tool class that raises an exception
        class ErrorTool(Tool):
            def __init__(self):
                super().__init__(
                    name="error_tool",
                    description="A tool that raises an error",
                    arguments=[
                        Argument("arg1", ArgumentType.STRING)
                    ]
                )
            
            def _execute(self, arg1):
                raise Exception("Tool error")
        
        # Return our error tool class
        mock_import_tool.return_value = ErrorTool
        
        call_text = """@tool error_tool
arg1: value1
@end"""
        exit_code, message = self.executor.execute(call_text)
        
        # The tool's execute method catches exceptions and returns UNKNOWN_ERROR (99)
        self.assertEqual(exit_code, ErrorCodes.UNKNOWN_ERROR)
        self.assertTrue("Error" in message)

    # Type validation tests
    def test_validate_string(self):
        self.assertEqual(validate_string("test"), "test")
        self.assertEqual(validate_string(""), "")
        
    def test_validate_boolean(self):
        self.assertTrue(validate_boolean("true"))
        self.assertTrue(validate_boolean("True"))
        self.assertTrue(validate_boolean("yes"))
        self.assertTrue(validate_boolean("y"))
        self.assertTrue(validate_boolean("1"))
        
        self.assertFalse(validate_boolean("false"))
        self.assertFalse(validate_boolean("False"))
        self.assertFalse(validate_boolean("no"))
        self.assertFalse(validate_boolean("n"))
        self.assertFalse(validate_boolean("0"))
        
        with self.assertRaises(ValueError):
            validate_boolean("invalid")
            
    def test_validate_int(self):
        self.assertEqual(validate_int("123"), 123)
        self.assertEqual(validate_int("-456"), -456)
        self.assertEqual(validate_int("0"), 0)
        
        with self.assertRaises(ValueError):
            validate_int("12.34")
        with self.assertRaises(ValueError):
            validate_int("not an int")
            
    def test_validate_float(self):
        self.assertEqual(validate_float("123.45"), 123.45)
        self.assertEqual(validate_float("-456.78"), -456.78)
        self.assertEqual(validate_float("0"), 0.0)
        self.assertEqual(validate_float("42"), 42.0)
        
        with self.assertRaises(ValueError):
            validate_float("not a float")
            
    def test_validate_filepath(self):
        self.assertEqual(validate_filepath("/path/to/file"), "/path/to/file")
        self.assertEqual(validate_filepath("relative/path"), "relative/path")
        self.assertEqual(validate_filepath("C:\\Windows\\Path"), "C:\\Windows\\Path")
        
        with self.assertRaises(ValueError):
            validate_filepath("")
            
    def test_validate_datetime(self):
        # Test full datetime format
        dt = validate_datetime("2023-04-05 14:30:45.123")
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 5)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 30)
        self.assertEqual(dt.second, 45)
        self.assertEqual(dt.microsecond, 123000)
        
        # Test with just year
        dt = validate_datetime("2023")
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)
        self.assertEqual(dt.hour, 0)
        self.assertEqual(dt.minute, 0)
        self.assertEqual(dt.second, 0)
        self.assertEqual(dt.microsecond, 0)
        
        # Test with year and month
        dt = validate_datetime("2023-04")
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 1)
        
        # Test with date only
        dt = validate_datetime("2023-04-05")
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 5)
        self.assertEqual(dt.hour, 0)
        
        # Test with date and hour
        dt = validate_datetime("2023-04-05 14")
        self.assertEqual(dt.year, 2023)
        self.assertEqual(dt.month, 4)
        self.assertEqual(dt.day, 5)
        self.assertEqual(dt.hour, 14)
        self.assertEqual(dt.minute, 0)
        
        # Test with invalid datetime
        with self.assertRaises(ValueError):
            validate_datetime("not a date")
        with self.assertRaises(ValueError):
            validate_datetime("2023-13-05")  # Invalid month
        with self.assertRaises(ValueError):
            validate_datetime("2023-04-31")  # Invalid day for April

    # Argument type conversion tests
    @patch.object(Executor, '_import_tool')
    def test_argument_types_conversion(self, mock_import_tool):
        mock_import_tool.return_value = TypedTool
        
        call_text = """@tool typed_tool
string_arg: test string
int_arg: 123
float_arg: 45.67
bool_arg: true
filepath_arg: /path/to/file
datetime_arg: 2023-04-05 14:30:45.123
@end"""
        
        exit_code, result = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("'string_arg': 'test string'", result)
        self.assertIn("'int_arg': 123", result)
        self.assertIn("'float_arg': 45.67", result)
        self.assertIn("'bool_arg': True", result)
        self.assertIn("'filepath_arg': '/path/to/file'", result)
        self.assertIn("'datetime_arg': datetime.datetime(2023, 4, 5, 14, 30, 45, 123000)", result)
        self.assertIn("'optional_arg': None", result)
        self.assertIn("'default_arg': 42", result)
    
    @patch.object(Executor, '_import_tool')
    def test_missing_required_argument(self, mock_import_tool):
        mock_import_tool.return_value = TypedTool
        
        call_text = """@tool typed_tool
string_arg: test string
int_arg: 123
float_arg: 45.67
bool_arg: true
@end"""
        
        exit_code, result = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, -1)
        self.assertIn("Missing required argument", result)
    
    @patch.object(Executor, '_import_tool')
    def test_invalid_argument_type(self, mock_import_tool):
        mock_import_tool.return_value = TypedTool
        
        call_text = """@tool typed_tool
string_arg: test string
int_arg: not_an_integer
float_arg: 45.67
bool_arg: true
filepath_arg: /path/to/file
datetime_arg: 2023-04-05 14:30:45.123
@end"""
        
        exit_code, result = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, -1)
        self.assertIn("Invalid value for int_arg", result)
    
    @patch.object(Executor, '_import_tool')
    def test_unknown_argument(self, mock_import_tool):
        mock_import_tool.return_value = TypedTool
        
        call_text = """@tool typed_tool
string_arg: test string
int_arg: 123
float_arg: 45.67
bool_arg: true
filepath_arg: /path/to/file
datetime_arg: 2023-04-05
unknown_arg: value
@end"""
        
        exit_code, result = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, -1)
        self.assertIn("Unknown argument: unknown_arg", result)
    
    @patch.object(Executor, '_import_tool')
    def test_default_value(self, mock_import_tool):
        mock_import_tool.return_value = TypedTool
        
        call_text = """@tool typed_tool
string_arg: test string
int_arg: 123
float_arg: 45.67
bool_arg: true
filepath_arg: /path/to/file
datetime_arg: 2023-04-05
@end"""
        
        exit_code, result = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("'default_arg': 42", result)
    
    @patch.object(Executor, '_import_tool')
    def test_optional_argument_provided(self, mock_import_tool):
        mock_import_tool.return_value = TypedTool
        
        call_text = """@tool typed_tool
string_arg: test string
int_arg: 123
float_arg: 45.67
bool_arg: true
filepath_arg: /path/to/file
datetime_arg: 2023-04-05
optional_arg: provided
@end"""
        
        exit_code, result = self.executor.execute(call_text)
        
        self.assertEqual(exit_code, ErrorCodes.SUCCESS)
        self.assertIn("'optional_arg': 'provided'", result)

if __name__ == '__main__':
    unittest.main() 