import os
import unittest
from unittest.mock import patch
from Tools.File.read import ReadFile
from Tools.error_codes import ErrorCodes
from Tools.base import ToolResult

class TestReadFile(unittest.TestCase):
    def setUp(self):
        self.tool = ReadFile()
        self.temp_dir = os.path.join(os.path.dirname(__file__), 'test_temp')
        os.makedirs(self.temp_dir, exist_ok=True)
        self.test_file = os.path.join(self.temp_dir, "test.txt")
        with open(self.test_file, 'w') as f:
            f.write("Test content")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            for root, dirs, files in os.walk(self.temp_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(self.temp_dir)

    def test_read_full_file(self):
        result = self.tool.execute(path=self.test_file)
        self.assertEqual(result.code, ErrorCodes.SUCCESS)
        self.assertEqual(result.message, "Test content")

    def test_read_partial_file(self):
        result = self.tool.execute(path=self.test_file, lines=1)
        self.assertEqual(result.code, ErrorCodes.SUCCESS)
        self.assertEqual(result.message, "Test content\n")

    def test_file_not_found(self):
        result = self.tool.execute(path="nonexistent.txt")
        self.assertEqual(result.code, ErrorCodes.RESOURCE_NOT_FOUND)
        self.assertIn("not found", result.message.lower())

    def test_directory_instead_of_file(self):
        result = self.tool.execute(path=self.temp_dir)
        self.assertEqual(result.code, ErrorCodes.INVALID_ARGUMENT_VALUE)
        self.assertIn("not a file", result.message.lower())

    @patch("builtins.open", side_effect=PermissionError("Permission denied"))
    def test_permission_denied(self, mock_open):
        result = self.tool.execute(path=self.test_file)
        self.assertEqual(result.code, ErrorCodes.PERMISSION_DENIED)
        self.assertIn("permission", result.message.lower())

    def test_invalid_line_count(self):
        result = self.tool.execute(path=self.test_file, lines="not_an_integer")
        self.assertEqual(result.code, ErrorCodes.INVALID_ARGUMENT_VALUE)
        self.assertIn("invalid", result.message.lower())

if __name__ == '__main__':
    unittest.main()
